# core.py
from .models import FeatureSpec, FeatureValue, TNode
from .yaml_parser import load_yaml
from collections import defaultdict
from omegaconf import OmegaConf
from hydra.utils import instantiate
from graphviz import Digraph
from easydict import EasyDict as edict


class Feature:
    def __init__(self, name: str, spec: OmegaConf):
        self.name = name
        # print(spec)
        self.feature_value = None
        self.spec = FeatureSpec(**spec)
        self.dependencies = self.spec.dependencies
        self.transformation = instantiate(self.spec.transformation)
        self.transformation_chain = TNode(
            **{"value": None, "transformation_name": "head"}
        )
        self.transformation_ptr = self.transformation_chain

    def compute(self, value, dependencies=None):
        # Apply the transformation function if specified
        if self.transformation:
            try:
                result = value
                for key, transformation_obj in self.transformation.items():
                    expects_data = transformation_obj.compile(dependencies)
                    if expects_data:
                        result = transformation_obj.execute(result)
                    else:
                        result = transformation_obj.execute()

                    transformation_node = TNode(
                        **{"value": result, "transformation_name": key}
                    )
                    self.transformation_ptr.next = transformation_node
                    self.transformation_ptr = transformation_node
            except Exception as e:
                self.print_transformation_chain()
                print(f"An error occurred during the transformation {key}: {e}")
                raise

        else:
            assert dependencies is None
            result = value

        # Validate the final result with FeatureValue
        self.feature_value = FeatureValue(value=result, data_type=self.spec.data_type)
        return self.feature_value.value

    def print_transformation_chain(self):
        current = self.transformation_chain.next
        chain_list = []
        while current:
            chain_list.append(
                f"(Transformation: {current.transformation_name}, Value: {current.value})"
            )
            current = current.next
        print("Transformation Chain: " + " -> ".join(chain_list))


class FeatureManager:
    def __init__(self, config_path: str, config_name: str):
        self.feature_specs: OmegaConf = load_yaml(
            config_path=config_path, config_name=config_name
        )

        self.independent_features: list[Feature] = []
        self.dependent_features: list[Feature] = []
        self.queue: list[Feature] = []

        self.features: edict = self._build_features()
        self.compile()

    def _build_features(self) -> edict:
        features = {}
        for name, spec in self.feature_specs.items():
            feature = Feature(name, spec)

            if not feature.dependencies:
                self.independent_features.append(feature)
            else:
                self.dependent_features.append(feature)

            features[name] = feature

        return edict(features)

    def compile(self):
        visited = defaultdict(int)
        for feature in self.independent_features:
            self.queue.append(feature)
            visited[feature.name] = 1
        dependent_features_sorted = sorted(
            self.dependent_features,
            key=lambda f: sum(visited[n] for n in f.dependencies),
            reverse=True,
        )
        for feature in dependent_features_sorted:
            self.queue.append(feature)
            visited[feature.name] = 1

    def get_visual_dependency_graph(
        self, save_plot: bool = False, output_file: str = "feature_dependencies"
    ):
        dot = Digraph(comment="Feature Dependencies")

        # Add nodes
        for feature in self.features.values():
            dot.node(feature.name)

        # Add edges
        for feature in self.features.values():
            for dependency in feature.dependencies:
                dot.edge(dependency, feature.name)

        if save_plot:
            # Save and render the graph
            dot.render(output_file, format="png")
            print(f"Dependencies graph saved as {output_file}.png")
        return dot

    def compute_all(self, data) -> edict:
        results = {}

        assert len(self.queue) == len(self.features)
        for feature in self.queue:
            name = feature.name
            is_independent = not feature.dependencies
            results[name] = feature.compute(
                value=data[name] if is_independent else 0,
                dependencies=None
                if is_independent
                else {f_name: self.features[f_name] for f_name in feature.dependencies},  # type: ignore[union-attr]
            )

        return edict(results)
