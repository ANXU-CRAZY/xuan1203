"""Huiyan routes shared by the main site and its bounded inference worker."""

from django.urls import path, re_path
from app_monitor import huiyan
from app_monitor import land_segmentation

urlpatterns = [
    path('huiyan/choose/', land_segmentation.choice_page, name='huiyan_choose'),
    path('huiyan/land/', land_segmentation.page, name='huiyan_land'),
    path('huiyan/land/release/', land_segmentation.release, name='huiyan_land_release'),
    re_path(r'^huiyan/land/workbench/(?P<upstream_path>.*)$', land_segmentation.proxy, name='huiyan_land_proxy'),
    path('huiyan/', huiyan.page, name='huiyan'),
    path('huiyan/api/status', huiyan.status, name='huiyan_status'),
    path('huiyan/api/geosearch', huiyan.geosearch, name='huiyan_geosearch'),
    path('huiyan/api/detect', huiyan.detect, name='huiyan_detect'),
    path('huiyan/api/detect_batch', huiyan.detect_batch, name='huiyan_detect_batch'),
    path('huiyan/api/convert', huiyan.convert, name='huiyan_convert'),
    path('huiyan/api/relabel', huiyan.relabel, name='huiyan_relabel'),
    path('huiyan/api/export_xlsx', huiyan.export_xlsx, name='huiyan_export_xlsx'),
    path('huiyan/api/tile', huiyan.tile, name='huiyan_tile'),
    re_path(r'^huiyan/api/tile/(?P<tile_path>.*)$', huiyan.tile, name='huiyan_tile_path'),
]
