# Copyright 2021-2023 NetCracker Technology Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from collections import OrderedDict
from typing import List, Dict

from . import thirdparties, SoftwareType, InternalCompatibility, CompatibilityMap, UpgradeConfig, UpgradeSoftware
from ..shell import run
from ..tracker import SummaryTracker, ComposedTracker


class KubernetesImagesResolver:
    def resolve(self, k8s_version: str) -> List[str]:
        kubeadm_path = thirdparties.resolve_local_path('/usr/bin/kubeadm', k8s_version)
        run(['chmod', '+x', kubeadm_path])
        return run([kubeadm_path, 'config', 'images', 'list', '--kubernetes-version', k8s_version]) \
            .strip().split('\n')


class KubernetesImages(SoftwareType):
    def __init__(self, compatibility: InternalCompatibility, upgrade_config: UpgradeConfig,
                 images_resolver: KubernetesImagesResolver):
        super().__init__(compatibility, upgrade_config)
        self.images_resolver = images_resolver

    @property
    def name(self) -> str:
        return 'kubernetes_images'

    def sync(self, summary_tracker: SummaryTracker) -> CompatibilityMap:
        """
        Fetch all kubernetes images from 'kubeadm' executable and actualize the compatibility_map.
        """
        k8s_versions = summary_tracker.all_k8s_versions
        k8s_images_mapping = get_k8s_images_mapping(self.images_resolver, k8s_versions)
        image_names = list(k8s_images_mapping)

        upgrade_software = UpgradeSoftware(self.upgrade_config, self.name, [])
        upgrade_software.prepare(summary_tracker)

        tracker = ComposedTracker(summary_tracker, upgrade_software)
        compatibility_map = self.compatibility.load(tracker, "kubernetes_images.yaml")
        compatibility_map.prepare(summary_tracker, image_names)

        for image_name in image_names:
            k8s_image_versions = k8s_images_mapping[image_name]
            compatibility_map.prepare_software_mapping(image_name, list(k8s_image_versions))

            for k8s_version, image_version in k8s_image_versions.items():
                k8s_settings = summary_tracker.kubernetes_versions[k8s_version]
                if image_name in k8s_settings:
                    image_version = k8s_settings[image_name]
                new_settings = {
                    'version': image_version
                }
                compatibility_map.reset_software_settings(image_name, k8s_version, new_settings)

        return compatibility_map


def get_k8s_images_mapping(images_resolver: KubernetesImagesResolver, k8s_versions: List[str]) -> Dict[str, Dict[str, str]]:
    k8s_images_mapping: Dict[str, Dict[str, str]] = OrderedDict()
    for k8s_version in k8s_versions:
        images_list = images_resolver.resolve(k8s_version)
        for item in images_list:
            image_path, version = item.split(':')
            image_name = '/'.join(image_path.split('/')[1:])
            k8s_images_mapping.setdefault(image_name, OrderedDict()).setdefault(k8s_version, version)

    return k8s_images_mapping
