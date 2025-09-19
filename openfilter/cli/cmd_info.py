import argparse
import inspect
import logging
import os

from openfilter.filter_runtime.filter import Filter

from .common import SCRIPT, get_filter

logger = logging.getLogger(__name__)

logger.setLevel(int(getattr(logging, (os.getenv('LOG_LEVEL') or 'INFO').upper())))

SHORTERHAND = {
    'filter':       'Filter',
    'imagein':      'ImageIn',
    'image_in':     'ImageIn',
    'mqtt':         'MQTTOut',
    'mqttout':      'MQTTOut',
    'mqtt_out':     'MQTTOut',
    'recorder':     'Recorder',
    'rest':         'REST',
    'util':         'Util',
    'video':        'Video',
    'vidin':        'VideoIn',
    'vid_in':       'VideoIn',
    'videoin':      'VideoIn',
    'video_in':     'VideoIn',
    'vidout':       'VideoOut',
    'vid_out':      'VideoOut',
    'videoout':     'VideoOut',
    'video_out':    'VideoOut',
    'webvis':       'Webvis',
}


# --- info -------------------------------------------------------------------------------------------------------------

def cmd_info(args):
    parser = argparse.ArgumentParser(prog=f'{SCRIPT} info', description='Get info on a specific Filter.')

    parser.add_argument('FILTER',
        help='Filter to show info on',
    )

    opts = parser.parse_args(args)

    logger.debug(f'opts: {opts}')

    # do the thing

    module_name, filter_name, module, filter_cls = get_filter(SHORTERHAND.get(opts.FILTER.lower(), opts.FILTER))

    for cls in inspect.getmro(filter_cls):
        if not issubclass(cls, Filter):
            continue

        if cls is not filter_cls:
            if cls is not Filter:
                print('\n\n^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nThe filter above is a subclass of the following:\n\n')

            else:
                print("\n\n^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nThe filter above is a subclass of the base Filter, see 'Filter' for information on that.")

                break

        print(f'{(s := f"{cls.__module__}.{cls.__qualname__}:")}\n{"-" * len(s)}\n')

        if not cls.__doc__:
            print('\nFilter class does not have a docstring.')
        else:
            print(inspect.cleandoc(cls.__doc__).strip())
