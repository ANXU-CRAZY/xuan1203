import json

from django.contrib.auth.models import User
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from rest_framework.authtoken.models import Token


class AccountRoutingTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user('routing-member', password='routing-password')
        self.manager = User.objects.create_user('routing-manager', password='routing-password',
                                                is_staff=True, is_superuser=True)

    def test_anonymous_entry_offers_separate_login_destinations(self):
        response = self.client.get('/account/')
        self.assertContains(response, '普通用户登录')
        self.assertContains(response, '管理员登录')
        self.assertContains(response, 'href="/login/"')
        self.assertContains(response, 'href="/admin/"')
        response = self.client.get('/login/')
        self.assertNotContains(response, 'adminLoginEntry')
        self.assertNotContains(response, '管理人员登录')
        self.assertContains(response, 'id="registerSection"')
        self.assertContains(response, 'href="#password-reset"')

    def test_home_login_choice_is_only_present_for_guests(self):
        self.assertContains(self.client.get('/'), 'id="account-login-dialog"')
        self.client.force_login(self.manager)
        self.assertNotContains(self.client.get('/'), 'id="account-login-dialog"')

    def test_admin_password_reset_entry_returns_to_admin_login(self):
        response = self.client.get('/admin/login/')
        self.assertContains(response, 'href="/login/?role=admin#password-reset"')
        response = self.client.get('/login/?role=admin')
        self.assertContains(response, '找回管理员密码')
        self.assertContains(response, 'data-login-url="/admin/login/"')
        self.assertContains(response, 'href="/admin/login/" class="reset-back"')
        response = self.client.get('/login/?role=https://example.com')
        self.assertContains(response, 'data-login-url="/login/"')

    def test_password_login_establishes_session_and_routes_by_role(self):
        for user, destination in ((self.member, '/profile/'), (self.manager, '/admin/')):
            client = Client(enforce_csrf_checks=True)
            credentials = {'username': user.username, 'password': 'routing-password'}
            self.assertEqual(client.post('/api/account/login/', credentials).status_code, 403)
            client.get('/login/')
            response = client.post('/api/account/login/', credentials,
                                   HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['next_url'], destination)
            self.assertIn('_auth_user_id', client.session)
            self.assertRedirects(client.get('/account/'), destination, fetch_redirect_response=False)
            self.assertRedirects(client.get('/login/'), destination, fetch_redirect_response=False)

    def test_existing_token_login_api_does_not_start_a_session(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/api/login/', {'username': self.member.username, 'password': 'routing-password'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'token'})
        self.assertNotIn('_auth_user_id', client.session)

    def test_admin_logout_clears_the_browser_login_state(self):
        self.client.force_login(self.manager)
        response = self.client.post('/admin/logout/')
        self.assertContains(response, "localStorage.removeItem('yb_token')")
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_existing_token_can_restore_session(self):
        for user, destination in ((self.member, '/profile/'), (self.manager, '/admin/')):
            token = Token.objects.create(user=user)
            client = Client(enforce_csrf_checks=True)
            response = client.post('/api/account/session/', HTTP_AUTHORIZATION='Token ' + token.key)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['next_url'], destination)
            self.assertRedirects(client.get('/account/'), destination, fetch_redirect_response=False)
            response = client.post('/api/account/logout/', HTTP_AUTHORIZATION='Token ' + token.key)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('_auth_user_id', client.session)

    def test_invalid_and_inactive_tokens_do_not_restore_session(self):
        client = Client()
        self.assertEqual(client.post('/api/account/session/', HTTP_AUTHORIZATION='Token invalid').status_code, 401)
        token = Token.objects.create(user=self.member)
        self.member.is_active = False
        self.member.save(update_fields=['is_active'])
        self.assertEqual(client.post('/api/account/session/', HTTP_AUTHORIZATION='Token ' + token.key).status_code, 401)
        self.assertNotIn('_auth_user_id', client.session)

    def test_admin_remains_chinese_with_english_browser(self):
        LogEntry.objects.create(user=self.manager, content_type=ContentType.objects.get_for_model(User),
                                object_id=str(self.member.pk), object_repr=self.member.username,
                                action_flag=CHANGE, change_message=json.dumps([
                                    {'changed': {'fields': ['Staff status', 'Superuser status']}},
                                ]))
        self.client.force_login(self.manager)
        response = self.client.get('/admin/', HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Language'], 'zh-hans')
        self.assertContains(response, json.dumps('登录令牌')[1:-1])
        self.assertContains(response, json.dumps('用户与权限')[1:-1])
        self.assertNotContains(response, 'Recent actions')
        self.assertNotContains(response, 'Staff status')
        self.assertNotContains(response, 'Superuser status')
        self.assertContains(response, '超级用户状态')
