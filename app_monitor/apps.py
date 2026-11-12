from django.apps import AppConfig

class AppMonitorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_monitor'
    verbose_name = '湿地监测系统'  # 【汉化关键】左侧菜单一级标题

    def ready(self):
        # 确保信号加载，用于积分自动发放
        import app_monitor.signals
        from django.apps import apps
        apps.get_app_config('auth').verbose_name = '用户与权限'
        apps.get_app_config('authtoken').verbose_name = '登录凭证'
        for model_name in ('Token', 'TokenProxy'):
            model = apps.get_model('authtoken', model_name)
            model._meta.verbose_name = '登录令牌'
            model._meta.verbose_name_plural = '登录令牌'
