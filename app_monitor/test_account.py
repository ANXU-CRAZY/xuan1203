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
