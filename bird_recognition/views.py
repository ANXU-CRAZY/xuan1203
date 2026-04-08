import io
import logging
import traceback
import torch
import numpy as np
from PIL import Image
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .serializers import ImageUploadSerializer
from .utils import load_detector, load_classifier, preprocess_image, classify_crop, _device

logger = logging.getLogger(__name__)

class BirdRecognitionView(APIView):
    # 禁用认证和权限，避免 DRF 介入 CSRF 检查
    authentication_classes = []
    permission_classes = []

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, format=None):
        serializer = ImageUploadSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"图片验证失败: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        image_file = serializer.validated_data['image']
        image_bytes = image_file.read()
        logger.info(f"收到图片: {image_file.name}, 大小: {len(image_bytes)} 字节")

        try:
            # 预处理现在返回四个值：填充后的图像、原始PIL图像、缩放比例ratio、填充的(left, top)
            img_np, original_pil, ratio, (pad_left, pad_top) = preprocess_image(image_bytes)
            logger.info(f"预处理完成，检测图像尺寸: {img_np.shape}, ratio={ratio:.4f}, pad=({pad_left},{pad_top})")
        except Exception as e:
            logger.error(f"图片解析失败: {e}\n{traceback.format_exc()}")
            return Response({'error': '图片格式错误或无法读取'}, status=status.HTTP_400_BAD_REQUEST)

        detector = load_detector()
        logger.info("检测模型加载成功")

        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        img_tensor = img_tensor.to(_device)

        param_dtype = next(detector.parameters()).dtype
        if img_tensor.dtype != param_dtype:
            img_tensor = img_tensor.to(param_dtype)
            logger.info(f"输入张量类型已转换为: {param_dtype}")

        try:
            with torch.no_grad():
                outputs = detector(img_tensor)
            logger.info(f"原始输出类型: {type(outputs)}")

            # 处理模型输出（可能是元组或张量）
            if isinstance(outputs, tuple):
                logger.info(f"输出元组长度: {len(outputs)}")
                for idx, item in enumerate(outputs):
                    if isinstance(item, torch.Tensor):
                        logger.info(f"  [{idx}] 张量形状: {item.shape}")
                    else:
                        logger.info(f"  [{idx}] 类型: {type(item)}")
                dets = outputs[0] if len(outputs) > 0 else torch.empty((0, 6))
            elif isinstance(outputs, torch.Tensor):
                dets = outputs
            else:
                logger.error(f"无法处理的输出类型: {type(outputs)}")
                dets = torch.empty((0, 6))

            if isinstance(dets, torch.Tensor):
                logger.info(f"检测输出形状: {dets.shape}")
                if dets.dim() == 3:
                    dets = dets[0]  # 取 batch 第一个
                elif dets.dim() != 2:
                    logger.error(f"不支持的张量维度: {dets.dim()}")
                    dets = torch.empty((0, 6))

                # 过滤低置信度
                if dets.shape[0] > 0:
                    conf_thres = 0.25
                    mask = dets[:, 4] > conf_thres
                    dets = dets[mask]
                logger.info(f"过滤后保留 {dets.shape[0]} 个目标")
            else:
                dets = torch.empty((0, 6))

        except Exception as e:
            logger.error(f"检测模型推理失败: {e}\n{traceback.format_exc()}")
            return Response({'error': '模型推理失败'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 解析结果并映射坐标到原始图像
        output = []
        if dets.shape[0] > 0:
            # 将原始 PIL 图像转为 numpy 数组用于裁剪
            original_np = np.array(original_pil)
            for i in range(dets.shape[0]):
                x1, y1, x2, y2, conf, cls_id = dets[i].tolist()
                # 将坐标从填充图像映射回原始图像
                x1 = (x1 - pad_left) / ratio
                y1 = (y1 - pad_top) / ratio
                x2 = (x2 - pad_left) / ratio
                y2 = (y2 - pad_top) / ratio
                # 转换为整数并限制在图像范围内
                x1, y1, x2, y2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
                x1 = max(0, min(x1, original_pil.width))
                y1 = max(0, min(y1, original_pil.height))
                x2 = max(x1, min(x2, original_pil.width))
                y2 = max(y1, min(y2, original_pil.height))
                cls_id = int(cls_id)

                if x1 >= x2 or y1 >= y2:
                    logger.warning(f"检测框无效，跳过")
                    continue

                # 从原始图像裁剪
                crop = original_np[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                # 细粒度分类
                try:
                    fine_class_id, fine_conf = classify_crop(crop)
                    logger.debug(f"分类结果: class={fine_class_id}, conf={fine_conf:.4f}")
                except Exception as e:
                    logger.error(f"分类器处理失败: {e}\n{traceback.format_exc()}")
                    fine_class_id, fine_conf = -1, 0.0

                output.append({
                    'detection_bbox': [x1, y1, x2, y2],
                    'detection_confidence': float(conf),
                    'detection_class_id': cls_id,
                    'fine_class_id': int(fine_class_id),
                    'fine_confidence': float(fine_conf)
                })

        return Response({'success': True, 'results': output}, status=status.HTTP_200_OK)