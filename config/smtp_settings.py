import os


def load_smtp_settings(base_dir):
    values = {}
    names = {
        'SMTP_HOST', 'SMTP_PORT', 'SMTP_USE_SSL', 'SMTP_USE_TLS', 'SMTP_USER',
        'SMTP_PASSWORD', 'SMTP_FROM', 'PASSWORD_RESET_HMAC_KEY', 'PASSWORD_RESET_TRUST_PROXY',
    }
    for name in ('.env', '.env.local'):
        path = base_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, separator, value = line.strip().partition('=')
            if separator and key.strip() in names:
                values[key.strip()] = value.strip().strip('"').strip("'")

    def get(key, default=''):
        return os.environ.get(key, values.get(key, default))

    def enabled(key, default='False'):
        return get(key, default).lower() in ('true', '1', 'yes')

    return {
        'EMAIL_HOST': get('SMTP_HOST', 'smtp.163.com'),
        'EMAIL_PORT': int(get('SMTP_PORT', '465')),
        'EMAIL_USE_SSL': enabled('SMTP_USE_SSL', 'True'),
        'EMAIL_USE_TLS': enabled('SMTP_USE_TLS'),
        'EMAIL_HOST_USER': get('SMTP_USER'),
        'EMAIL_HOST_PASSWORD': get('SMTP_PASSWORD'),
        'DEFAULT_FROM_EMAIL': get('SMTP_FROM'),
        'EMAIL_TIMEOUT': 10,
        'PASSWORD_RESET_HMAC_KEY': get('PASSWORD_RESET_HMAC_KEY'),
        'PASSWORD_RESET_TRUST_PROXY': enabled('PASSWORD_RESET_TRUST_PROXY'),
    }
