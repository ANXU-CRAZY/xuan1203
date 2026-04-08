import os
import io
import cv2
import torch
import numpy as np
from PIL import Image
import ultralytics  # 确保已安装

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETECTOR_PATH = os.path.join(BASE_DIR, 'bird_recognition', 'yolo_model', 'detector.pt')
CLASSIFIER_PATH = os.path.join(BASE_DIR, 'bird_recognition', 'yolo_model', 'classifier.pt')

_detector = None
_classifier = None
_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def load_detector():
    global _detector
    if _detector is None:
        checkpoint = torch.load(DETECTOR_PATH, map_location=_device, weights_only=False)
        if isinstance(checkpoint, dict) and 'model' in checkpoint:
            _detector = checkpoint['model']
        else:
            _detector = checkpoint
        _detector.eval()
    return _detector

def load_classifier():
    global _classifier
    if _classifier is None:
        checkpoint = torch.load(CLASSIFIER_PATH, map_location=_device, weights_only=False)
        if isinstance(checkpoint, dict) and 'model' in checkpoint:
            _classifier = checkpoint['model']
        else:
            _classifier = checkpoint
        _classifier.eval()
    return _classifier

def letterbox(img, new_shape=640, color=(114,114,114), return_info=False):
    """
    缩放并填充图像，保持宽高比。
    参数:
        img: 输入图像 (H, W, C)
        new_shape: 目标尺寸 (h, w) 或 int
        color: 填充颜色
        return_info: 如果为 True，返回 (img, ratio, (left, top))
    返回:
        填充后的图像，如果 return_info=True 则额外返回 ratio 和填充的 (left, top)
    """
    shape = img.shape[:2]  # [h, w]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # 缩放比例
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    dw /= 2
    dh /= 2

    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    if return_info:
        return img, r, (left, top)
    return img

def preprocess_image(image_bytes, target_size=640):
    """
    将图片字节流转换为模型输入所需的 numpy 数组。
    返回：
        img_rgb: 填充后的 RGB 图像 (用于检测)
        original_pil: 原始 PIL 图像 (用于预览和裁剪)
        ratio: 缩放比例
        pad: 填充的 (left, top)
    """
    pil_img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    original_pil = pil_img.copy()
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    img, ratio, pad = letterbox(img, new_shape=target_size, color=(114,114,114), return_info=True)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img_rgb, original_pil, ratio, pad

def classify_crop(crop_np):
    """
    对裁剪出的目标区域进行分类。
    参数:
        crop_np: numpy 数组 (H, W, C)，RGB 格式
    返回:
        (class_id, confidence)
    """
    classifier = load_classifier()
    # 预处理：resize 到分类器输入大小（假设 224x224）
    crop_resized = cv2.resize(crop_np, (224, 224))
    crop_tensor = torch.from_numpy(crop_resized).permute(2,0,1).unsqueeze(0).float() / 255.0
    crop_tensor = crop_tensor.to(_device)

    # 确保输入类型与模型权重一致
    param_dtype = next(classifier.parameters()).dtype
    if crop_tensor.dtype != param_dtype:
        crop_tensor = crop_tensor.to(param_dtype)

    with torch.no_grad():
        outputs = classifier(crop_tensor)
        # 处理输出为元组的情况（例如 Ultralytics 分类模型返回 (logits, 其他)）
        if isinstance(outputs, (tuple, list)):
            logits = outputs[0]  # 假设第一个元素是 logits
        else:
            logits = outputs

        if not isinstance(logits, torch.Tensor):
            raise TypeError(f"无法处理的输出类型: {type(logits)}")

        probs = torch.softmax(logits, dim=1)
        confidence, class_id = torch.max(probs, dim=1)

    return class_id.item(), confidence.item()