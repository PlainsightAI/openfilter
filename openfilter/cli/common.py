import importlib
import json
import logging
import os

from openfilter.filter_runtime.filter import Filter, FilterConfig, is_mq_addr
from openfilter.filter_runtime.utils import json_getval, split_commas_maybe
from typing import List, Tuple, Type

logger = logging.getLogger(__name__)

level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
level = logging._nameToLevel.get(level_name, logging.INFO)
logger.setLevel(level)

SCRIPT = "openfilter"

PARAM_ORDER = list(FilterConfig.__annotations__)

SHORTHAND = {
    "Filter": "openfilter.filter_runtime.filter.Filter",
    "ImageIn": "openfilter.filter_runtime.filters.image_in.ImageIn",
    "MQTTOut": "openfilter.filter_runtime.filters.mqtt_out.MQTTOut",
    "Recorder": "openfilter.filter_runtime.filters.recorder.Recorder",
    "REST": "openfilter.filter_runtime.filters.rest.REST",
    "Util": "openfilter.filter_runtime.filters.util.Util",
    "Video": "openfilter.filter_runtime.filters.video.Video",
    "VideoIn": "openfilter.filter_runtime.filters.video_in.VideoIn",
    "VideoOut": "openfilter.filter_runtime.filters.video_out.VideoOut",
    "Webvis": "openfilter.filter_runtime.filters.webvis.Webvis",
    # 'Vid2GS':      'filter_vid2gs.vid2gs.Vid2GS',
    # 'OuroboREST':  'filter_rest_wrapper.filter_rest_wrapper.FilterOuroboREST',
}

DOCKER_IMAGES = {
    "filter_runtime.filters.image_in.ImageIn": "us-west1-docker.pkg.dev/plainsightai-prod/oci/image_in",
    "filter_runtime.filters.mqtt_out.MQTTOut": "us-west1-docker.pkg.dev/plainsightai-prod/oci/mqtt_out",
    "filter_runtime.filters.recorder.Recorder": "us-west1-docker.pkg.dev/plainsightai-prod/oci/recorder",
    "filter_runtime.filters.rest.REST": "us-west1-docker.pkg.dev/plainsightai-prod/oci/rest",
    "filter_runtime.filters.util.Util": "us-west1-docker.pkg.dev/plainsightai-prod/oci/util",
    "filter_runtime.filters.video_in.VideoIn": "us-west1-docker.pkg.dev/plainsightai-prod/oci/video_in",
    "filter_runtime.filters.video_out.VideoOut": "us-west1-docker.pkg.dev/plainsightai-prod/oci/video_out",
    "filter_runtime.filters.webvis.Webvis": "us-west1-docker.pkg.dev/plainsightai-prod/oci/webvis",
    # 'filter_vid2gs.vid2gs.Vid2GS',: 'plainsight.jfrog.io/docker-int/filters/???',
    # 'filter_rest_wrapper.filter_rest_wrapper.FilterOuroboREST',: 'plainsight.jfrog.io/docker-int/filters/???',
}


def only_mq_addr(addr: str) -> str:
    """just the address part without topics, options or ephemeral indicator, only used for tcp:// and ipc:// so don't
    have to deal with '!' password bs."""

    return addr[
        : min(
            addr.find("?") & 0xFFFFFFFF,
            addr.find(";") & 0xFFFFFFFF,
            addr.find("!") & 0xFFFFFFFF,
        )
    ]


def get_filter(name: str):
    """Get a filter module and class by a shorthand or fully qualified name."""

    module_name, filter_name = SHORTHAND.get(name, name).rsplit(".", 1)
    module = importlib.import_module(module_name)

    if not (filter_cls := getattr(module, filter_name, None)):
        raise ValueError(f"invalid filter {name}")

    return module_name, filter_name, module, filter_cls


def filter_can_do_filter_outputs(filter_cls):
    """Check if a Filter has MQ outputs to other filters possibly in a very thread-unsafe way."""

    if (filter_type := filter_cls.FILTER_TYPE) == "Input":
        return True
    elif filter_type == "Output":
        return False

    class FilterConfigNormalizeCheck(BaseException):
        pass

    def normalize_config_check_outputs(config):
        raise (FilterConfigNormalizeCheck(config))

    old_Filter_normalize_config, Filter.normalize_config = (
        Filter.normalize_config,
        normalize_config_check_outputs,
    )  # VERY UNSAFE

    try:
        filter_cls.normalize_config(dict(outputs="tcp://test_filter_output:12345"))
    except FilterConfigNormalizeCheck as exc:
        return exc.args[0].get("outputs") == "tcp://test_filter_output:12345"
    except Exception:
        return False  # safest thing to do here
    finally:
        Filter.normalize_config = old_Filter_normalize_config

    return False  # juuust in case something weird happened (class did not pass normalize_config() call down to Filter)


def parse_filters(
    args: list[str], ipc: bool = False
) -> List[Tuple[Type, dict, str]]:  # -> [(filter class, config, referenced name), ...]  - [(filter_example.example.Example, {...}, 'Example')]
    """Parse command args to list of filter classes and configs."""

    if not args:
        raise ValueError(f"must specify at least one Filter")

    # build list of filter classes with their configs

    def parse_param_value(arg):
        if "=" in arg:  # --param=value
            param, value = arg.split("=", 1)

            if (
                value
            ):  # empty string here means no value provided, not empty string value provided
                return param, json_getval(value)

        elif args and not nextarg.startswith("-"):  # --param value
            if (
                value := args.pop()
            ):  # empty string here means no value provided, not empty string value provided
                return arg, json_getval(value)

        elif arg.startswith("no-"):  # --no-param --other switch or end
            return arg[3:], False
        else:  # --param (--other switch or end)
            return (
                arg,
                True,
            )  # this also indicates no value for params that expect values

        return None, None

    filters = []

    while args:
        module_name, filter_name, module, filter_cls = get_filter(args.pop())

        config = FilterConfig()

        filters.append((filter_cls, config, filter_name))

        while args:
            arg = args.pop()
            nextarg = args[-1] if args else None

            if arg == "-":  # end of this filter
                break
            if not arg.startswith("-"):
                raise ValueError(f"invalid option {arg!r}")

            if arg[1] == "-":  # config var
                if not (arg := arg[2:]):
                    raise ValueError(f"empty '--' config option not allowed")

                param, value = parse_param_value(arg)

                if param is not None:
                    config[param] = value

                continue

            # single '-' option like '-env'

            param, value = parse_param_value(arg[1:])

            if param is None:
                continue

            if param == "env":
                args.extend(
                    [f"-env-compose={(v := json.dumps(value))}", f"-env-run={v}"]
                )

            elif (is_run := param == "env-run") or param == "env-compose":
                if len(var_val := value.split("=", 1)) < 2:
                    raise ValueError(f"environment variable {value!r} missing value")

                if (
                    env := config.get(
                        name := "__env_run" if is_run else "__env_compose"
                    )
                ) is None or env == "":
                    env = config[name] = {}

                env[var_val[0]] = var_val[1]

            else:
                raise ValueError(f"invalid option {arg!r}")

    filter_id_configs = (
        {}
    )  # {'filter_name': [config, ...], ...}, only filters which don't already have id

    for _, config, filter_name in filters:
        if (
            config.sources is True
        ):  # correct for setting empty `sources` or `outputs` via "... --sources -..."
            config.sources = None  # this is different from 'sources' actually not present in the config at all
        if config.outputs is True:
            config.outputs = None

        if (
            config.id is None
        ):  # build list of filters without id sharing same class in order to decide between single or multi-with-digit naming
            filter_id_configs.setdefault(filter_name, []).append(config)

    for (
        filter_name,
        configs,
    ) in (
        filter_id_configs.items()
    ):  # autoset config.id not set by user, 'filter_name', or 'filter_name1', 'filter_name2', ...
        if len(configs) == 1:
            configs[0].id = filter_name

        else:
            for i, config in enumerate(configs, 1):
                config.id = f"{filter_name}{i}"

    config_by_id = {}  # {'config.id': config, ...}

    for _, config, _ in filters:  # error on duplicate ids
        if config.id in config_by_id:
            raise ValueError(f"duplicate id {config.id!r} not allowed")

        config_by_id[config.id] = config

    # all the following has to do with mapping id sources to addresses and autochaining filters

    last_source = None

    for (
        filter_cls,
        config,
        _,
    ) in (
        filters
    ):  # set source by id for any filter that doesn't have (anything including None) to previous filter in list
        if last_source and "sources" not in config:
            config.sources = last_source

        if ("outputs" not in config or config.outputs) and filter_can_do_filter_outputs(
            filter_cls
        ):
            last_source = config.id

        if (
            "sources" in config and not config.sources
        ):  # convert "--sources=" empty assign to no sources
            del config.sources
        if (
            "outputs" in config and not config.outputs
        ):  # convert "--outputs=" empty assign to no outputs
            del config.outputs

    max_port = 5548
    non_mq_output_ids = set()
    source_by_id = {}  # {'config.id': 'tcp://localhost:5550', ...}

    for (
        _,
        config,
        _,
    ) in filters:  # build list of used ports and also default source by id (if present)
        if not (outputs := split_commas_maybe(config.outputs)):
            continue

        if any(
            not is_mq_addr(output) for output in outputs
        ):  # if any output is not a message queue address ('tcp://' or 'ipc://') then we exclude it from potentail autochain
            non_mq_output_ids.add(config.id)

            continue

        for output in reversed(
            outputs
        ):  # reversed to leave the first output as default
            if output.startswith("tcp://"):
                max_port = max(
                    max_port,
                    int((only_mq_addr(output[6:]).rsplit(":", 1) + [5550])[:2][1]),
                )

        output = only_mq_addr(output)

        if output.startswith(
            "tcp://"
        ):  # parse 'tcp://' source and reserve ports, 'ipc://' output is unchanged as source
            addr, port = (output[6:].rsplit(":", 1) + ["5550"])[:2]
            output = f'tcp://{"localhost" if addr[:1] in "*0" else addr}:{port}'

        source_by_id[config.id] = (
            output  # set first output as default source for this filter
        )

    for (
        _,
        config,
        _,
    ) in (
        filters
    ):  # convert id sources to actual sources and add outputs to referenced filters which don't have them
        if not (sources := split_commas_maybe(config.sources)):
            continue

        for i, source in enumerate(sources):
            if not isinstance(source, str):  # TODO: handle structures?
                raise ValueError(
                    f"this CLI does not currently handle source structures, as in {source}"
                )
            if is_mq_addr(
                source
            ):  # already pointing to real address, no further processing needed
                continue
            if not (
                id_config := config_by_id.get(id := only_mq_addr(source))
            ):  # not an mq addr or known config.id, safest thing is to skip it
                continue

            if id in non_mq_output_ids:
                raise ValueError(f"filter {id!r} can not be used as a source")
            if id == config.id:
                raise ValueError(f"filter {id!r} can not use itself as a source")

            if id_source := source_by_id.get(
                id
            ):  # already had default source, use that
                sources[i] = id_source + source[len(id) :]
            elif id_config.outputs:
                raise ValueError(
                    f"something wrong, {id!r} should not have any outputs at this point"
                )

            else:
                if ipc:
                    source_by_id[id] = new_source = f"ipc://{id_config.id}"
                    id_config.outputs = new_source

                else:
                    source_by_id[id] = new_source = (
                        f"tcp://localhost:{(max_port := max_port + 2)}"
                    )
                    id_config.outputs = f"tcp://*:{max_port}"

                sources[i] = new_source + source[len(id) :]

                logger.info(f"add {id}.outputs={id_config.outputs!r}")

            logger.info(f"add {config.id}.sources={sources[i]!r}")

        config.sources = ", ".join(sources)

    # return filters

    filters = [
        (
            cls,
            FilterConfig(
                {  # sort them config params all nice and purdy
                    **{k: config[k] for k in PARAM_ORDER if k in config},
                    **{k: v for k, v in config.items() if k not in PARAM_ORDER},
                }
            ),
            name,
        )
        for cls, config, name in filters
    ]

    return filters
