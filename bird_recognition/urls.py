from django.urls import path
from .views import BirdRecognitionView

urlpatterns = [
    path('recognize/', BirdRecognitionView.as_view(), name='bird-recognize'),
]