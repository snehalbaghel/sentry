from __future__ import absolute_import

import six
import logging

from django.utils.translation import ugettext_lazy as _


from sentry.integrations import (
    IntegrationInstallation,
    IntegrationFeatures,
    IntegrationProvider,
    IntegrationMetadata,
    FeatureDescription,
)
from sentry.pipeline import NestedPipelineView
from sentry.identity.pipeline import IdentityProviderPipeline
from sentry.utils.http import absolute_uri
from sentry.models import Project, ProjectKey
from sentry.utils.compat import map
from sentry.shared_integrations.exceptions import IntegrationError, ApiError

from .client import VercelClient

logger = logging.getLogger("sentry.integrations.vercel")

DESCRIPTION = """
VERCEL DESC
"""

FEATURES = [
    FeatureDescription(
        """
        DEPLOYMENT DESCRIPTION
        """,
        IntegrationFeatures.DEPLOYMENT,
    ),
]


metadata = IntegrationMetadata(
    description=DESCRIPTION.strip(),
    features=FEATURES,
    author="The Sentry Team",
    noun=_("Installation"),
    issue_url="https://github.com/getsentry/sentry/issues/new?title=Vercel%20Integration:%20&labels=Component%3A%20Integrations",
    source_url="https://github.com/getsentry/sentry/tree/master/src/sentry/integrations/vercel",
    aspects={},
)


class VercelIntegration(IntegrationInstallation):
    def get_client(self):
        access_token = self.model.metadata["access_token"]
        if self.model.metadata["installation_type"] == "team":
            return VercelClient(access_token, self.model.external_id)

        return VercelClient(access_token)

    def get_organization_config(self):
        vercel_client = self.get_client()
        # TODO: add try/catch if we get API failure
        vercel_projects = [
            {"value": p["id"], "label": p["name"]} for p in vercel_client.get_projects()
        ]

        proj_fields = ["id", "platform", "name", "slug"]
        sentry_projects = map(
            lambda proj: {key: proj[key] for key in proj_fields},
            (
                Project.objects.filter(organization_id=self.organization_id)
                .order_by("slug")
                .values(*proj_fields)
            ),
        )

        fields = [
            {
                "name": "project_mappings",
                "type": "project_mapper",
                "mappedDropdown": {
                    "items": vercel_projects,
                    "placeholder": "Select a Vercel Project",  # TOOD: add translation
                },
                "sentryProjects": sentry_projects,
            }
        ]

        return fields

    def update_organization_config(self, mappings):
        # mappings = {"project_mappings": [[sentry_project_id, vercel_project_id]]}

        metadata = self.model.metadata
        vercel_client = VercelClient(metadata["access_token"], metadata.get("team_id"))
        sentry_project_id = mappings["project_mappings"][0][0]
        vercel_project_id = mappings["project_mappings"][0][1]
        org = Project.objects.filter(id=sentry_project_id).get()
        sentry_project = Project.objects.filter(id=sentry_project_id).get()
        sentry_project_dsn = ProjectKey.objects.filter(project=sentry_project).get()

        data = {
            "name": "SENTRY_ORG_test",
            "value": org.slug,
        }
        sentry_org_secret = self.create_secret(vercel_client, vercel_project_id, data)

        sentry_org_data = {"key": data["name"], "value": sentry_org_secret, "target": "production"}

        self.create_env_var(vercel_client, vercel_project_id, sentry_org_data)

        data["name"] = "SENTRY_PROJECT"
        data["value"] = sentry_project.slug
        sentry_project_secret = self.create_secret(vercel_client, vercel_project_id, data)

        sentry_project_data = {
            "key": data["name"],
            "value": sentry_project_secret,
            "target": "production",
        }
        self.create_env_var(vercel_client, vercel_project_id, sentry_project_data)

        data["name"] = "NEXT_PUBLIC_SENTRY_DSN"
        data["value"] = sentry_project_dsn.get_dsn(public=True)
        sentry_dsn_secret = self.create_secret(vercel_client, vercel_project_id, data)

        sentry_dsn_data = {"key": data["name"], "value": sentry_dsn_secret, "target": "production"}
        self.create_env_var(vercel_client, vercel_project_id, sentry_dsn_data)

    def get_env_vars(self, client, vercel_project_id):
        get_env_var_url = "/v5/projects/%s/env"
        return client.get(path=get_env_var_url % vercel_project_id)

    def already_exists(self, client, vercel_project_id, data):
        exists = False
        existing_env_vars = self.get_env_vars(client, vercel_project_id)["envs"]
        for env_var in existing_env_vars:
            if env_var["key"] == data["name"]:
                exists = True
                break
        return exists

    def create_secret(self, client, vercel_project_id, data):
        secrets_url = "/v2/now/secrets"
        if not self.already_exists(client, vercel_project_id, data):
            try:
                client.post(path=secrets_url, data=data)["uid"]
            except ApiError:
                raise

    def create_env_var(self, client, vercel_project_id, data):
        env_var_url = "/v4/projects/%s/env"
        try:
            client.post(path=env_var_url % vercel_project_id, data=data)
        except ApiError:
            raise


class VercelIntegrationProvider(IntegrationProvider):
    key = "vercel"
    name = "Vercel"
    requires_feature_flag = True
    metadata = metadata
    integration_cls = VercelIntegration
    features = frozenset([IntegrationFeatures.DEPLOYMENT])
    oauth_redirect_url = "/extensions/vercel/configure/"

    def get_pipeline_views(self):
        identity_pipeline_config = {"redirect_url": absolute_uri(self.oauth_redirect_url)}

        identity_pipeline_view = NestedPipelineView(
            bind_key="identity",
            provider_key=self.key,
            pipeline_cls=IdentityProviderPipeline,
            config=identity_pipeline_config,
        )

        return [identity_pipeline_view]

    def build_integration(self, state):
        data = state["identity"]["data"]
        access_token = data["access_token"]
        team_id = data.get("team_id")
        client = VercelClient(access_token, team_id)

        if team_id:
            external_id = team_id
            installation_type = "team"
            team = client.get_team()
            name = team["name"]
        else:
            external_id = data["user_id"]
            installation_type = "user"
            user = client.get_user()
            name = user["name"]

        try:
            webhook = client.create_deploy_webhook()
        except ApiError as err:
            logger.info(
                "vercel.create_webhook.failed",
                extra={"error": six.text_type(err), "external_id": external_id},
            )
            try:
                details = err.json["messages"][0].values().pop()
            except Exception:
                details = "Unknown Error"
            message = u"Could not create deployment webhook in Vercel: {}".format(details)
            raise IntegrationError(message)

        integration = {
            "name": name,
            "external_id": external_id,
            "metadata": {
                "access_token": access_token,
                "installation_id": data["installation_id"],
                "installation_type": installation_type,
                "webhook_id": webhook["id"],
            },
        }

        return integration
