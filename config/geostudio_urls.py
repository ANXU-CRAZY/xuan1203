from django.urls import path
from app_monitor import workbench, workbench_agent, workbench_processing, workbench_sidecar
from app_monitor.geostudio_login import sign_in, sign_out

urlpatterns = [
    path('', workbench.page, name='home'),
    path('workbench/', workbench.page, name='workbench'),
    path('account/', sign_in, name='account_entry'),
    path('logout/', sign_out, name='geostudio_logout'),
    path('huiyan/', workbench.page, name='huiyan_choose'),
    path('workbench/agent/plan/', workbench_agent.plan, name='workbench_agent_plan'),
    path('ai/v1/chat/completions', workbench_agent.native_chat, name='workbench_agent_native_policy'),
    path('sidecar/<path:path>', workbench_sidecar.proxy, name='workbench_sidecar'),
    path('workbench/analysis/whitebox/', workbench_processing.whitebox_start, name='workbench_whitebox_start'),
    path('workbench/analysis/artifact/<str:directory>/<int:index>/', workbench_processing.whitebox_artifact, name='workbench_whitebox_artifact'),
    path('workbench/geolibre/', workbench.engine, name='workbench_engine'),
    path('workbench/geolibre/<path:asset>', workbench.engine, name='workbench_engine_asset'),
]
