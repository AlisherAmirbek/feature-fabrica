import copy
from collections.abc import Callable
from textwrap import dedent
from typing import Any

from hydra._internal.instantiate._instantiate2 import (
    _call_target, _convert_node, _is_target, _Keys,
    _prepare_input_dict_or_list)
from hydra._internal.utils import _locate
from hydra.errors import InstantiationException
from hydra.types import ConvertMode, TargetConf
from omegaconf import DictConfig, OmegaConf
from omegaconf._utils import is_structured_config

from feature_fabrica._internal.instantiate.expressions.fefa_expressions import (
    _hydrate_fefa_expression, _is_valid_expression)


def instantiate(config: Any, *args: Any, **kwargs: Any) -> Any:
    """
    :param config: An config object describing what to call and what params to use.
                   In addition to the parameters, the config must contain:
                   _target_ : target class or callable name (str)
                   And may contain:
                   _recursive_: Construct nested objects as well (bool).
                                True by default.
                                may be overridden via a _recursive_ key in
                                the kwargs
                   _convert_: Conversion strategy
                        none    : Passed objects are DictConfig and ListConfig, default
                        partial : Passed objects are converted to dict and list, with
                                  the exception of Structured Configs (and their fields).
                        object  : Passed objects are converted to dict and list.
                                  Structured Configs are converted to instances of the
                                  backing dataclass / attr class.
                        all     : Passed objects are dicts, lists and primitives without
                                  a trace of OmegaConf containers. Structured configs
                                  are converted to dicts / lists too.
                   _partial_: If True, return functools.partial wrapped method or object
                              False by default. Configure per target.
    :param args: Optional positional parameters pass-through
    :param kwargs: Optional named parameters to override
                   parameters in the config object. Parameters not present
                   in the config objects are being passed as is to the target.
                   IMPORTANT: dataclasses instances in kwargs are interpreted as config
                              and cannot be used as passthrough
    :return: if _target_ is a class name: the instantiated object
             if _target_ is a callable: the return value of the call
    """

    # Return None if config is None
    if config is None:
        return None

    # TargetConf edge case
    if isinstance(config, TargetConf) and config._target_ == "???":
        # Specific check to give a good warning about failure to annotate _target_ as a string.
        raise InstantiationException(
            dedent(
                f"""\
                Config has missing value for key `_target_`, cannot instantiate.
                Config type: {type(config).__name__}
                Check that the `_target_` key in your dataclass is properly annotated and overridden.
                A common problem is forgetting to annotate _target_ as a string : '_target_: str = ...'"""
            )
        )
        # TODO: print full key

    if isinstance(config, (dict, list)):
        config = _prepare_input_dict_or_list(config)

    kwargs = _prepare_input_dict_or_list(kwargs)

    # Structured Config always converted first to OmegaConf
    if is_structured_config(config) or isinstance(config, (dict, list)):
        config = OmegaConf.structured(config, flags={"allow_objects": True})

    if OmegaConf.is_dict(config):
        # Finalize config (convert targets to strings, merge with kwargs)
        config_copy = copy.deepcopy(config)
        config_copy._set_flag(
            flags=["allow_objects", "struct", "readonly"], values=[True, False, False]
        )
        config_copy._set_parent(config._get_parent())
        config = config_copy

        if kwargs:
            config = OmegaConf.merge(config, kwargs)

        OmegaConf.resolve(config)

        _recursive_ = config.pop(_Keys.RECURSIVE, True)
        _convert_ = config.pop(_Keys.CONVERT, ConvertMode.NONE)
        _partial_ = config.pop(_Keys.PARTIAL, False)

        instantiated_config = instantiate_node(
            config, *args, recursive=_recursive_, convert=_convert_, partial=_partial_
        )

        return instantiated_config
    elif OmegaConf.is_list(config):
        # Finalize config (convert targets to strings, merge with kwargs)
        config_copy = copy.deepcopy(config)
        config_copy._set_flag(
            flags=["allow_objects", "struct", "readonly"], values=[True, False, False]
        )
        config_copy._set_parent(config._get_parent())
        config = config_copy

        OmegaConf.resolve(config)

        _recursive_ = kwargs.pop(_Keys.RECURSIVE, True)
        _convert_ = kwargs.pop(_Keys.CONVERT, ConvertMode.NONE)
        _partial_ = kwargs.pop(_Keys.PARTIAL, False)

        if _partial_:
            raise InstantiationException(
                "The _partial_ keyword is not compatible with top-level list instantiation"
            )

        instantiated_config = instantiate_node(
            config, *args, recursive=_recursive_, convert=_convert_, partial=_partial_
        )
        return instantiated_config

    else:
        raise InstantiationException(
            dedent(
                f"""\
                Cannot instantiate config of type {type(config).__name__}.
                Top level config must be an OmegaConf DictConfig/ListConfig object,
                a plain dict/list, or a Structured Config class or instance."""
            )
        )

def _resolve_target(
    target: str | type | Callable[..., Any], full_key: str
) -> type | Callable[..., Any]:
    """Resolve target string, type or callable into type or callable."""
    if isinstance(target, str):
        if _is_valid_expression(target):
            hydrated_target = _hydrate_fefa_expression(target)
            return hydrated_target
        try:
            target = _locate(target)
        except Exception as e:
            msg = f"Error locating target '{target}', set env var HYDRA_FULL_ERROR=1 to see chained exception."
            if full_key:
                msg += f"\nfull_key: {full_key}"
            raise InstantiationException(msg) from e
    if not callable(target):
        msg = f"Expected a callable target, got '{target}' of type '{type(target).__name__}'"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise InstantiationException(msg)
    return target

def _resolve_target_node(node: DictConfig, args: Any, full_key: str, convert: str | ConvertMode = ConvertMode.NONE,
                         recursive: bool = True, partial: bool = False,):
    exclude_keys = set({"_target_", "_convert_", "_recursive_", "_partial_"})
    _target_ = _resolve_target(node.get(_Keys.TARGET), full_key)
    if OmegaConf.is_config(_target_):
        if _is_target(_target_):
            return _resolve_target_node(_target_, args, full_key, convert, recursive, partial)
        else:
            return instantiate_node(_target_, args, full_key, convert, recursive, partial)

    kwargs = {}
    is_partial = node.get("_partial_", False) or partial
    for key in node.keys():
        if key not in exclude_keys:
            if OmegaConf.is_missing(node, key) and is_partial:
                continue
            value = node[key]
            if recursive:
                value = instantiate_node(
                    value, convert=convert, recursive=recursive
                )
            kwargs[key] = _convert_node(value, convert)

    return _call_target(_target_, partial, args, kwargs, full_key)

def instantiate_node(
    node: Any,
    *args: Any,
    convert: str | ConvertMode = ConvertMode.NONE,
    recursive: bool = True,
    partial: bool = False,
) -> Any:

    # Return None if config is None
    if node is None or (OmegaConf.is_config(node) and node._is_none()):
        return None

    if not OmegaConf.is_config(node):
        return node

    # Override parent modes from config if specified
    if OmegaConf.is_dict(node):
        # using getitem instead of get(key, default) because OmegaConf will raise an exception
        # if the key type is incompatible on get.
        convert = node[_Keys.CONVERT] if _Keys.CONVERT in node else convert
        recursive = node[_Keys.RECURSIVE] if _Keys.RECURSIVE in node else recursive
        partial = node[_Keys.PARTIAL] if _Keys.PARTIAL in node else partial

    full_key = node._get_full_key(None)

    if not isinstance(recursive, bool):
        msg = f"Instantiation: _recursive_ flag must be a bool, got {type(recursive)}"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    if not isinstance(partial, bool):
        msg = f"Instantiation: _partial_ flag must be a bool, got {type( partial )}"
        if node and full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    # If OmegaConf list, create new list of instances if recursive
    if OmegaConf.is_list(node):
        items = [
            instantiate_node(item, convert=convert, recursive=recursive)
            for item in node._iter_ex(resolve=True)
        ]

        if convert in (ConvertMode.ALL, ConvertMode.PARTIAL, ConvertMode.OBJECT):
            # If ALL or PARTIAL or OBJECT, use plain list as container
            return items
        else:
            # Otherwise, use ListConfig as container
            lst = OmegaConf.create(items, flags={"allow_objects": True})
            lst._set_parent(node)
            return lst

    elif OmegaConf.is_dict(node):
        if _is_target(node):
            resolved_target_node = _resolve_target_node(node, args, full_key, convert, recursive, partial)
            return resolved_target_node

        else:
            # If ALL or PARTIAL non structured or OBJECT non structured,
            # instantiate in dict and resolve interpolations eagerly.
            if convert == ConvertMode.ALL or (
                convert in (ConvertMode.PARTIAL, ConvertMode.OBJECT)
                and node._metadata.object_type in (None, dict)
            ):
                dict_items = {}
                for key, value in node.items():
                    # list items inherits recursive flag from the containing dict.
                    instantiated_node = instantiate_node(
                        value, convert=convert, recursive=recursive
                    )
                    if OmegaConf.is_dict(instantiated_node):
                        for node_key, node_value in instantiated_node.items():
                            dict_items[f"{key}_{node_key}"] = node_value
                    else:
                        dict_items[key] = instantiated_node

                return dict_items
            else:
                # Otherwise use DictConfig and resolve interpolations lazily.
                cfg = OmegaConf.create({}, flags={"allow_objects": True})
                for key, value in node.items():
                    instantiated_node = instantiate_node(
                        value, convert=convert, recursive=recursive
                    )
                    if OmegaConf.is_dict(instantiated_node):
                        for node_key, node_value in instantiated_node.items():
                            cfg[f"{key}_{node_key}"] = node_value
                    else:
                        cfg[key] = instantiated_node
                cfg._set_parent(node)
                cfg._metadata.object_type = node._metadata.object_type
                if convert == ConvertMode.OBJECT:
                    return OmegaConf.to_object(cfg)
                return cfg

    else:
        assert False, f"Unexpected config type : {type(node).__name__}"
