from rest_framework import serializers

class ImageUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(required=True)

    def validate_image(self, value):
        # 文件大小限制（10MB）
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError("图片大小不能超过10MB")

        # 允许的MIME类型
        allowed_types = ['image/jpeg', 'image/png', 'image/bmp']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("不支持的图片格式，仅支持 JPEG、PNG、BMP")

        return value