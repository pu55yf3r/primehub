import unittest
import os
from unittest import mock

import tornado
from kubespawner.objects import make_pod
from tornado.testing import AsyncTestCase

from jupyterhub_profiles import PrimeHubSpawner, OIDCAuthenticator
from jinja2 import Environment, FileSystemLoader

template_loader = Environment(loader=FileSystemLoader(['tests/fixtures', 'fixtures']))

import jupyterhub_profiles


def mock_spawner():
    spawner = PrimeHubSpawner(_mock=True)

    def mock_render_html(template_name, local_vars):
        template = template_loader.get_template(template_name)
        return template.render(local_vars)

    spawner.render_html = mock_render_html
    return spawner


def create_spawner_with_default_group():
    spawner = mock_spawner()
    spawner._groups = [{'id': 'phusers',
                        'name': 'phusers',
                        'displayName': 'auto generated by bootstrap',
                        'enabledSharedVolume': False,
                        'sharedVolumeCapacity': None,
                        'homeSymlink': None,
                        'launchGroupOnly': None,
                        'quotaCpu': None,
                        'quotaGpu': 0,
                        'quotaMemory': None,
                        'projectQuotaCpu': None,
                        'projectQuotaGpu': 0,
                        'projectQuotaMemory': None,
                        'instanceTypes': [{'name': 'cpu-only',
                                           'displayName': 'cpu-only',
                                           'description': 'auto generated by bootstrap',
                                           'spec': {'description': 'auto generated by bootstrap',
                                                    'displayName': 'cpu-only',
                                                    'limits.cpu': 1,
                                                    'limits.memory': '1G',
                                                    'limits.nvidia.com/gpu': 0,
                                                    'requests.cpu': 1,
                                                    'requests.memory': '1G'},
                                           'global': False}],
                        'images': [{'name': 'base-notebook',
                                    'displayName': 'base-notebook',
                                    'description': 'auto generated by bootstrap',
                                    'spec': {'description': 'auto generated by bootstrap',
                                             'displayName': 'base-notebook',
                                             'type': 'both',
                                             'urlForGpu': 'jupyter/base-notebook',
                                             'url': 'jupyter/base-notebook'},
                                    'global': False}],
                        'datasets': []
                        }]

    def _get_container_resource_usage(group):
        return 0, 0, 0

    spawner.get_container_resource_usage = _get_container_resource_usage
    return spawner


class FakeAuthenticator(OIDCAuthenticator):

    def get_custom_resources(self, namespace, plural):
        return []

    pass


async def _get_auth_state():
    return {'oauth_user': {'sub': '71ab5174-c163-42b0-8573-0a6b9ff7306f',
                           'email_verified': True,
                           'project-quota': {'gpu': 0},
                           'roles': ['uma_authorization',
                                     'offline_access',
                                     'ds:foo',
                                     'img:base-notebook',
                                     'ds:abc',
                                     'it:cpu-only'],
                           'quota': {'gpu': 0},
                           'groups': ['/phusers',
                                      '/everyone'],
                           'preferred_username': 'phadmin'},
            'scope': ['openid',
                      'profile',
                      'email'],
            'launch_context': {'id': '71ab5174-c163-42b0-8573-0a6b9ff7306f',
                               'username': 'phadmin',
                               'isAdmin': True,
                               'volumeCapacity': None,
                               'groups': [{'name': 'phusers',
                                           'displayName': 'auto generated by bootstrap',
                                           'enabledSharedVolume': False,
                                           'sharedVolumeCapacity': None,
                                           'homeSymlink': None,
                                           'launchGroupOnly': None,
                                           'quotaCpu': None,
                                           'quotaGpu': 0,
                                           'quotaMemory': None,
                                           'projectQuotaCpu': None,
                                           'projectQuotaGpu': 0,
                                           'projectQuotaMemory': None,
                                           'instanceTypes': [{'name': 'cpu-only',
                                                              'displayName': 'cpu-only',
                                                              'description': 'auto generated by bootstrap',
                                                              'spec': {'description': 'auto generated by bootstrap',
                                                                       'displayName': 'cpu-only',
                                                                       'limits.cpu': 1,
                                                                       'limits.memory': '1G',
                                                                       'limits.nvidia.com/gpu': 0,
                                                                       'requests.cpu': 1,
                                                                       'requests.memory': '1G'},
                                                              'global': False}],
                                           'images': [{'name': 'base-notebook',
                                                       'displayName': 'base-notebook',
                                                       'description': 'auto generated by bootstrap',
                                                       'spec': {'description': 'auto generated by bootstrap',
                                                                'displayName': 'base-notebook',
                                                                'type': 'both',
                                                                'url': 'jupyter/base-notebook',
                                                                'urlForGpu': 'jupyter/base-notebook'},
                                                       'global': False}],
                                           'datasets': []},
                                          {'name': 'everyone',
                                           'displayName': 'Global',
                                           'enabledSharedVolume': False,
                                           'sharedVolumeCapacity': None,
                                           'homeSymlink': None,
                                           'launchGroupOnly': None,
                                           'quotaCpu': 0,
                                           'quotaGpu': 0,
                                           'quotaMemory': None,
                                           'projectQuotaCpu': 0,
                                           'projectQuotaGpu': 0,
                                           'projectQuotaMemory': None,
                                           'instanceTypes': [],
                                           'images': [],
                                           'datasets': []}]},
            'system': {'defaultUserVolumeCapacity': 20}}


class KernelGatewayTest(AsyncTestCase):

    @tornado.testing.gen_test
    def test_spawn_disable_feature_and_user_select_it(self):
        jupyterhub_profiles.enable_feature_kernel_gateway = False

        spawner = create_spawner_with_default_group()

        form_data = {'group': ['phusers'],
                     'instance_type': ['cpu-only'],
                     'image': ['base-notebook'],
                     'kernel_gateway': ['on']}

        spawner.options_from_form(form_data)
        spawner.user_options['group'] = dict(name='phusers')
        spawner.user.get_auth_state = _get_auth_state

        yield FakeAuthenticator().pre_spawn_start(spawner.user, spawner)
        pod_spec = spawner.get_pod_manifest().result().to_dict()

        # it should be same with old behavior, one init_container and only run notebook container
        self.assertEqual(1, len(pod_spec['spec']['init_containers']))
        self.assertEqual("admission-is-not-found", pod_spec['spec']['init_containers'][0]['name'])
        self.assertEqual(1, len(pod_spec['spec'].get('containers', [])))

    @tornado.testing.gen_test
    def test_spawn_enable_feature_and_user_not_select_it(self):
        jupyterhub_profiles.enable_feature_kernel_gateway = True

        spawner = create_spawner_with_default_group()

        form_data = {'group': ['phusers'],
                     'instance_type': ['cpu-only'],
                     'image': ['base-notebook'],
                     # 'kernel_gateway': ['on']
                     }

        spawner.options_from_form(form_data)
        spawner.user_options['group'] = dict(name='phusers')
        spawner.user.get_auth_state = _get_auth_state

        yield FakeAuthenticator().pre_spawn_start(spawner.user, spawner)
        pod_spec = spawner.get_pod_manifest().result().to_dict()

        # it should be same with old behavior, one init_container and only run notebook container
        self.assertEqual(1, len(pod_spec['spec']['init_containers']))
        self.assertEqual("admission-is-not-found", pod_spec['spec']['init_containers'][0]['name'])
        self.assertEqual(1, len(pod_spec['spec'].get('containers', [])))

    @tornado.testing.gen_test
    def test_spawn_enable_feature_and_user_select_it(self):
        jupyterhub_profiles.enable_feature_kernel_gateway = True

        spawner = create_spawner_with_default_group()

        # set the gpu request to verify resources setting on the kernel container
        spawner._groups[0]['instanceTypes'][0]['spec']['limits.nvidia.com/gpu'] = 1

        # set the image to verify it change to kernel container
        spawner._groups[0]['images'][0]['spec']['url'] = 'keroro/base-notebook'
        spawner._groups[0]['images'][0]['spec']['urlForGpu'] = 'keroro/base-notebook-gpu'

        form_data = {'group': ['phusers'],
                     'instance_type': ['cpu-only'],
                     'image': ['base-notebook'],
                     'kernel_gateway': ['on']
                     }

        spawner.options_from_form(form_data)
        spawner.user_options['group'] = dict(name='phusers')
        spawner.user.get_auth_state = _get_auth_state

        yield FakeAuthenticator().pre_spawn_start(spawner.user, spawner)
        pod_spec = spawner.get_pod_manifest().result().to_dict()

        # # it should be same with old behavior, no init_container and only run notebook container
        # self.assertTrue(pod_spec['spec']['init_containers'] is None)
        # self.assertEqual(1, len(pod_spec['spec'].get('containers', [])))
        init_container = pod_spec['spec']['init_containers'][0]
        self.assertEqual('chown', init_container['name'])
        self.assertEqual('busybox', init_container['image'])
        self.assertEqual({'runAsUser': 0}, init_container['security_context'])

        notebook_container, kernel_container = pod_spec['spec']['containers']
        self.assertEqual('notebook', notebook_container['name'])
        self.assertEqual('kernel', kernel_container['name'])

        # resources should be empty in notebook and set in the kernel
        self.assertEqual({'limits': {}, 'requests': {}}, notebook_container['resources'])
        self.assertEqual(
            {'limits': {'cpu': 1.0, 'memory': '1G', 'nvidia.com/gpu': 1}, 'requests': {'cpu': 1.0, 'memory': '1G'}},
            kernel_container['resources'])

        # check image for notebook and kernel
        # when launch with kernel container, we set the default image from spwaner.image
        # it should be empty string if no helm value
        self.assertEqual('', notebook_container['image'])

        # user selected notebook will set to kernel container
        self.assertEqual('keroro/base-notebook-gpu', kernel_container['image'])
