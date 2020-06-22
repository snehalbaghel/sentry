from __future__ import absolute_import

import responses

from six.moves.urllib.parse import parse_qs, urlencode
from sentry.shared_integrations.exceptions import ApiError
from sentry.integrations.vercel import VercelIntegrationProvider
from sentry.models import (
    Integration,
    OrganizationIntegration,
)
from sentry.testutils import IntegrationTestCase


class VercelIntegrationTest(IntegrationTestCase):
    provider = VercelIntegrationProvider

    def assert_setup_flow(self, is_team=False):
        responses.reset()

        access_json = {
            "user_id": "my_user_id",
            "access_token": "my_access_token",
            "installation_id": "my_config_id",
        }

        if is_team:
            team_query = "?teamId=my_team_id"
            access_json["team_id"] = "my_team_id"
            responses.add(
                responses.GET,
                "https://api.vercel.com/v1/teams/my_team_id%s" % team_query,
                json={"name": "my_team_name"},
            )
        else:
            team_query = ""
            responses.add(
                responses.GET,
                "https://api.vercel.com/www/user",
                json={"user": {"name": "my_user_name"}},
            )

        responses.add(
            responses.POST, "https://api.vercel.com/v2/oauth/access_token", json=access_json
        )

        responses.add(
            responses.GET,
            "https://api.vercel.com/v4/projects/%s" % team_query,
            json={"projects": []},
        )

        responses.add(
            responses.POST,
            "https://api.vercel.com/v1/integrations/webhooks%s" % team_query,
            json={"id": "webhook-id"},
        )

        resp = self.client.get(u"{}?{}".format(self.setup_path, urlencode({"code": "oauth-code"}),))

        mock_request = responses.calls[0].request
        req_params = parse_qs(mock_request.body)
        assert req_params["grant_type"] == ["authorization_code"]
        assert req_params["code"] == ["oauth-code"]
        assert req_params["redirect_uri"] == ["http://testserver/extensions/vercel/configure/"]
        assert req_params["client_id"] == ["vercel-client-id"]
        assert req_params["client_secret"] == ["vercel-client-secret"]

        assert resp.status_code == 200
        self.assertDialogSuccess(resp)

        integration = Integration.objects.get(provider=self.provider.key)

        external_id = "my_team_id" if is_team else "my_user_id"
        name = "my_team_name" if is_team else "my_user_name"
        installation_type = "team" if is_team else "user"

        assert integration.external_id == external_id
        assert integration.name == name
        assert integration.metadata == {
            "access_token": "my_access_token",
            "installation_id": "my_config_id",
            "installation_type": installation_type,
            "webhook_id": "webhook-id",
        }
        assert OrganizationIntegration.objects.get(
            integration=integration, organization=self.organization
        )

    @responses.activate
    def test_team_flow(self):
        self.assert_setup_flow(is_team=True)

    @responses.activate
    def test_user_flow(self):
        self.assert_setup_flow(is_team=False)

    @responses.activate
    def test_update_organization_config(self):
        with self.tasks():
            self.assert_setup_flow()

        # mock org secret
        responses.add(
            responses.GET,
            "https://api.vercel.com/v3/now/secrets/%s" % "sentry_org",
            body=ApiError('The secret "%s" was not found.' % "sentry_org"),
            status=404,
        )
        responses.add(
            responses.POST, "https://api.vercel.com/v2/now/secrets", json={"uid": "sec_123"},
        )

        # mock project secret
        responses.add(
            responses.GET,
            "https://api.vercel.com/v3/now/secrets/%s" % "sentry_project_1",
            body=ApiError('The secret "%s" was not found.' % "sentry_project_1"),
            status=404,
        )
        responses.add(
            responses.POST, "https://api.vercel.com/v2/now/secrets", json={"uid": "sec_456"},
        )
        # mock DSN secret
        responses.add(
            responses.GET,
            "https://api.vercel.com/v3/now/secrets/%s" % "next_sentry_dsn_1",
            body=ApiError('The secret "%s" was not found.' % "next_sentry_dsn_1"),
            status=404,
        )
        responses.add(
            responses.POST, "https://api.vercel.com/v2/now/secrets", json={"uid": "sec_789"},
        )

        # mock org env var
        responses.add(
            responses.POST,
            "https://api.vercel.com/v4/projects/%s/env"
            % "Qme9NXBpguaRxcXssZ1NWHVaM98MAL6PHDXUs1jPrgiM8H",
            json={
                "value": "sec_123",
                "target": "production",
                "configurationId": 1,
                "key": "blah",
                "createdAt": 1592849410863,
                "updatedAt": 1592849410863,
                "system": False,
            },
        )
        # mock project env var
        responses.add(
            responses.POST,
            "https://api.vercel.com/v4/projects/%s/env"
            % "Qme9NXBpguaRxcXssZ1NWHVaM98MAL6PHDXUs1jPrgiM8H",
            json={
                "value": "sec_456",
                "target": "production",
                "configurationId": 1,
                "key": "blah",
                "createdAt": 1592849410863,
                "updatedAt": 1592849410863,
                "system": False,
            },
        )
        # mock dsn env var
        responses.add(
            responses.POST,
            "https://api.vercel.com/v4/projects/%s/env"
            % "Qme9NXBpguaRxcXssZ1NWHVaM98MAL6PHDXUs1jPrgiM8H",
            json={
                "value": "sec_789",
                "target": "production",
                "configurationId": 1,
                "key": "blah",
                "createdAt": 1592849410863,
                "updatedAt": 1592849410863,
                "system": False,
            },
        )
        # assert all the calls were made w/ the right args
        # org = self.organization
        # integration = Integration.objects.get(provider=self.provider.key)
        # installation = integration.get_installation(org.id)
        # data = {"project_mappings": [[1, "Qme9NXBpguaRxcXssZ1NWHVaM98MAL6PHDXUs1jPrgiM8H"],]}
        # installation = integration.get_installation(self.organization)
        # org_integration = OrganizationIntegration.objects.get(
        #     organization_id=org.id, integration_id=integration.id
        # )
        # config = org_integration.config
        # assert config == {}
        # installation.update_organization_config(data)
        # assert config == {
        #     "project_mappings": [[2, "Qme9NXBpguaRxcXssZ1NWHVaM98MAL6PHDXUs1jPrgiM8H"],]
        # }

    @responses.activate
    def test_update_org_config_vars_exist(self):
        # test where the secret and env var already exist
        pass

    @responses.activate
    def test_upgrade_org_config_no_dsn(self):
        # test where there is no enabled DSN
        pass
