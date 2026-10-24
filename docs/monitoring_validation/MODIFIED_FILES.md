# 本次业务及验证文件

业务代码与首次验收记录（035c611 → 76725eb）：

- app_monitor/monitoring.py
- app_monitor/static/app_monitor/geo/protected_areas.geojson
- app_monitor/static/app_monitor/monitoring.css
- app_monitor/static/app_monitor/monitoring.js
- app_monitor/static/app_monitor/site-shell.js
- app_monitor/static/app_monitor/site-theme.css
- app_monitor/templates/app_monitor/site_theme.html
- app_monitor/templates/article-detail.html
- app_monitor/templates/articles.html
- app_monitor/templates/image-gallery.html
- app_monitor/templates/index.html
- app_monitor/templates/species-detail.html
- app_monitor/templates/species-gallery.html
- app_monitor/templates/species.html
- app_monitor/test_monitoring.py
- app_monitor/views.py
- config/urls.py
- docs/monitoring_validation/DISPLAY_RECHECK.md
- docs/monitoring_validation/PROTECTED_AREA.md
- docs/monitoring_validation/REPORT.md
- docs/monitoring_validation/SITE_NAVIGATION_THEME.md
- docs/monitoring_validation/browser_check.py
- docs/monitoring_validation/check_progressive.py
- docs/monitoring_validation/check_protected_area.py
- docs/monitoring_validation/check_site_navigation.py
- docs/monitoring_validation/database-results.json
- docs/monitoring_validation/database_check.py
- docs/monitoring_validation/display-recheck-results.json
- docs/monitoring_validation/progressive-results.json
- docs/monitoring_validation/protected-area-results.json
- docs/monitoring_validation/recheck_display.py
- docs/monitoring_validation/run_tests.py
- docs/monitoring_validation/vivid-navigation-results.json
- scripts/convert_protected_area.py
- scripts/shapefile_readers.py
- static/vendor/chart.js/chart.umd.min.js
- static/vendor/font-awesome/all.min.css
- static/vendor/font-awesome/webfonts/fa-brands-400.woff2
- static/vendor/font-awesome/webfonts/fa-regular-400.woff2
- static/vendor/font-awesome/webfonts/fa-solid-900.woff2
- static/vendor/jquery/jquery-3.6.0.min.js
- static/vendor/leaflet/images/layers-2x.png
- static/vendor/leaflet/images/layers.png
- static/vendor/leaflet/images/marker-icon-2x.png
- static/vendor/leaflet/images/marker-icon.png
- static/vendor/leaflet/images/marker-shadow.png
- static/vendor/leaflet/leaflet.css
- static/vendor/leaflet/leaflet.js
- templates/bird-guess.html
- templates/bird-runner.html
- templates/floating-island.html
- templates/login.html
- templates/migration.html
- templates/profile.html
- templates/report.html
- templates/wetland-detective.html
- templates/wetland-restorer.html

上线验收追加：DEPLOYMENT.md、MODIFIED_FILES.md、可配置目标地址的验证脚本、check_production_smoke.py和production-*-results.json。

未纳入用户原有删除项、未跟踪报告/图片、配置密钥、数据库与模型文件。
