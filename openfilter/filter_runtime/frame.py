"""Frame object which contains an `image` (optionally jpg compressed) and a dictionary `data` object. Attempts to
minimize format conversions and redundant jpg encoding. So that for example if a jpg encoded image comes from the
network, and it is only read, that the jpg data is available on the way out without having to reencode.

WARNING! Grayscale hasn't gotten all the love it probably deserves.
"""

from typing import Any, Literal, Union

import cv2
import numpy as np
from numpy import ndarray

from openfilter.observability.tracing import maybe_start_span

__all__ = ['ShapeAndFormat', 'Frame']

ShapeAndFormat = tuple[tuple[int, int, int] | tuple[int, int], str]


class Frame:
    """Frame with attached data dictionary. Automatic handling and caching and passthrough of jpg encoded image. Also
    convenience functions for RGB/BGR/GRAY and RW/RO.

    Create:
        Frame(image: ndarray | None, data: dict | None, format: str | None)  - if data is None then set to empty {}
        Frame(image: ndarray | None, data: Frame,       format: str | None)  - data copied from Frame, also format if not provided
        Frame(image: Frame,          data: dict | None, format: str | None)  - if data is None then copied from Frame, image (including cached jpg) copied from Frame
        Frame(image: dict)                                                   - data-only frame, leave the others None as they have no effect

        Frame.from_jpg(jpg: buffer,  data: dict | None, height: int, width: int, format: str)  - format must be one of FORMATS

    Notes:
        * Use 'frame.rw_rgb' in place of "frame.rw.rgb' or 'frame.rgb.rw', it will always give the most efficient
        conversion from whatever you start with. Obiously same for '.ro' and '.bgr'.
    """

    image:     np.ndarray | None  # be aware can be readonly, in order to guarantee writable .image use 'frame.rw.image'
    data:      dict[str, Any]

    shapef:    ShapeAndFormat | None
    shape:     tuple[int, int, int] | tuple[int, int] | None
    format:    str | None
    height:    int | None
    width:     int | None
    channels:  int | None

    jpg:       bytearray | bytes | None
    has_jpg:   bool | None
    has_raw:   bool | None
    has_image: bool

    is_rw:     bool | None
    is_ro:     bool | None
    is_rgb:    bool | None
    is_bgr:    bool | None
    is_gray:   bool | None

    rw:        'Frame'
    ro:        'Frame'
    rgb:       'Frame'
    bgr:       'Frame'
    gray:      'Frame'

    rw_rgb:    'Frame'
    rw_bgr:    'Frame'
    ro_rgb:    'Frame'
    ro_bgr:    'Frame'

    fullstr:   str

    __image:   np.ndarray | Literal[False] | None
    __data:    dict[str, Any]
    __jpg:     bytes | bytearray | Literal[False] | None
    __shapef:  ShapeAndFormat | None


    FORMATS          = ('RGB', 'BGR', 'GRAY')
    FORMATS_AND_NONE = FORMATS + (None,)

    def __init__(self,
        image:  Union[np.ndarray, 'Frame', dict, None] = None,
        data:   Union[dict, 'Frame', None] = None,
        format: Union[str, 'Frame', None] = None,
    ):
        if isinstance(image, dict):
            self.__image = self.__jpg = self.__shapef = None
            self.__data  = image

        elif isinstance(image, Frame):
            self.__image  = image.__image
            self.__data   = image.__data if data is None else data.__data if isinstance(data, Frame) else data
            self.__jpg    = image.__jpg
            self.__shapef = shapef if (shapef := image.__shapef) is None or \
                (format := Frame.validate_format_or_Frame(format)) is None else (shapef[0], format)

        else:  # isinstance(image, (ndarray, NoneType))
            self.__image = image

            if not isinstance(data, Frame):
                self.__data = {} if data is None else data

            else:
                self.__data = data.__data

                if format is None:
                    format = (shapef := data.__shapef) and shapef[1]

            if image is None:
                self.__shapef = self.__jpg = None

            else:
                self.__jpg = False  # False means jpg of valid image not created yet because None means no image at all

                if (lshape := len(shape := image.shape)) == 2:
                    self.__shapef = (shape, 'GRAY')
                elif lshape != 3 or shape[2] != 3:
                    raise ValueError('invalid image')
                elif (format := Frame.validate_format_or_Frame(format)) is None:
                    raise ValueError('must specify format here')
                else:
                    self.__shapef = (shape, format)

    def __eq__(self, other):
        return not (
            not isinstance(other, Frame) or
            other.__data != self.__data or
            (is_None := other.__image is None) ^ (self.__image is None) or
            (not is_None and not np.array_equal(other.image, self.image))
        )

    def __reduce__(self):
        return (Frame.unreduce, (image := self.__image, self.__data, self.__jpg, self.__shapef,
            image.flags.writeable if isinstance(image, ndarray) else None))

    @staticmethod
    def unreduce(image, data, jpg, shapef, writeable):
        frame          = Frame()
        frame.__image  = image
        frame.__data   = data
        frame.__jpg    = jpg
        frame.__shapef = shapef

        if isinstance(image, ndarray) and writeable != image.flags.writeable:  # this is why we did our own serialization, the readable state is important during testing
            try:
                image.flags.writeable = writeable
            except Exception:
                pass

        return frame

    @staticmethod
    def validate_format_or_Frame(format: Union[str, 'Frame', None]) -> str:
        """Allows None as a format, keep this in mind if you only want an ACTUAL format and check for it yourself."""

        if isinstance(format, Frame):
            return (shapef := format.__shapef) and shapef[1]

        if format not in Frame.FORMATS_AND_NONE:
            raise ValueError(f'invalid format {format!r}, must be one of {Frame.FORMATS_AND_NONE}')

        return format

    @staticmethod
    def validate_format(format: Union[str, 'Frame', None]) -> str:
        """Allows None as a format, keep this in mind if you only want an ACTUAL format and check for it yourself."""

        if format not in Frame.FORMATS_AND_NONE:
            raise ValueError(f'invalid format {format!r}, must be one of {Frame.FORMATS_AND_NONE}')

        return format

    def __repr__(self):
        if (image := self.__image) is None:
            return 'Frame(None)'

        xtra = (
            '-jpg' if image is False else
            '+jpg' if self.__jpg else
            '-ro' if not image.flags.writeable else
            ''
        )

        return f'Frame({self.width}x{self.height}x{self.format}{xtra})'

    @staticmethod
    def decode(blob: bytes | bytearray, format: str | None):
        # frame.decode_jpg span fires only when wrapped by an outer mq.recv hop span;
        # otherwise the helper is a single is_recording() check (no Span allocated).
        with maybe_start_span("frame.decode_jpg", {"frame.format": format or "BGR"}):
            image = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR if format != 'GRAY' else 0)
        if image is None:
            raise ValueError('the provided image blob is invalid or in an unsupported format')

        return image

    @staticmethod
    def from_blob(
        blob:   bytes | bytearray,  # or object with buffer interface
        data:   dict | None = None,
        height: int | None = None,
        width:  int | None = None,
        format: str | None = None,
    ) -> 'Frame':
        """Make a Frame from an encoded image, could be anything that opencv supports. The reason this function exists
        is not convenience but rather that if the image is jpg then it is not decoded immediately but rather added as a
        cached __jpg to be decoded on need. But if not needed and it is to be sent directly over the network then
        expensive encoding will not need to be performed."""

        if not isinstance(blob, (bytes, bytearray)):
            blob = bytearray(memoryview(blob))

        Frame.validate_format(format)

        frame       = Frame(data)
        frame.__jpg = blob if (is_jpg := blob[:2] == b'\xff\xd8') else False

        if (have_dims := height is not None and width is not None) and is_jpg:
            frame.__image  = False
            frame.__shapef = ((height, width) if format == 'GRAY' else (height, width, 3), format or 'BGR')

        else:
            frame.__image  = image = Frame.decode(blob, format)
            frame.__shapef = (image.shape, format or 'BGR')

            if is_jpg:
                image.flags.writeable = False

            if have_dims:
                assert image.shape[:2] == (height, width), f'blob decoded dimensions {image.shape[:2]} do not match specified dimensions {(height, width)}'

        return frame

    from_jpg = from_blob

    def copy(self) -> 'Frame':
        """Make a copy of a self, shallow copy of data, image copy of writable image, no copy if image is readonly."""

        copy = Frame(self, self.__data.copy())

        if isinstance(image := self.__image, ndarray) and image.flags.writeable:
            copy.__image = image.copy()

        return copy

    @property
    def image(self):
        """May decode jpg-only frame to ro image if only had jpg and no image yet."""

        if (image := self.__image) is False:
            self.__image          = image = Frame.decode(self.__jpg, self.__shapef[1])
            image.flags.writeable = False

            assert image.shape == self.__shapef[0], f'jpg decoded shape {image.shape} does not match specified shape {self.__shapef[0]}'

        return image

    @property
    def data(self):
        return self.__data

    @property
    def shapef(self):
        return self.__shapef

    @property
    def shape(self):
        return None if (shapef := self.__shapef) is None else shapef[0]

    @property
    def format(self):
        return None if (shapef := self.__shapef) is None else shapef[1]

    @property
    def height(self):
        return None if (shapef := self.__shapef) is None else shapef[0][0]

    @property
    def width(self):
        return None if (shapef := self.__shapef) is None else shapef[0][1]

    @property
    def channels(self):
        return None if (shapef := self.__shapef) is None else 1 if shapef[1] == 'GRAY' else 3

    @property
    def jpg(self):
        """Potentially caching jpg encoding, or maybe it came from the network originally encoded and is already
        available. A jpg is always returned, it is cached in self for future returns if self is readonly."""

        if (jpg := self.__jpg) is False:
            image    = self.__image
            # frame.encode_jpg span fires only when wrapped by an outer mq.send hop span.
            with maybe_start_span("frame.encode_jpg", {"frame.format": (self.__shapef[1] if self.__shapef else "") or ""}):
                res, buf = cv2.imencode('.jpg', image)

            if not res:
                raise RuntimeError('jpg encoding failed')

            buf.flags.writeable = False  # so that jpg isn't writable, no I won't repeat numpy spelling mistakes!
            jpg                 = bytearray(memoryview(buf))

            if not image.flags.writeable:  # if we are a readonly image then cache encoded jpg
                self.__jpg = jpg

        return jpg

    @property
    def has_jpg(self):
        """Whether this Frame already has an encoded jpg ready for return without having to encode."""

        return None if (jpg := self.__jpg) is None else jpg is not False

    @property
    def has_raw(self):
        """Whether this Frame has a decoded raw image, will be False for jpg-only image that hasn't been decoded yet."""

        return None if (image := self.__image) is None else image is not False

    @property
    def has_image(self):
        """Whether this Frame has an image of any kind (not None), because accessing .image to check this may decode."""

        return self.__image is not None

    @property
    def is_rw(self):
        return None if (image := self.__image) is None else False if image is False else image.flags.writeable

    @property
    def is_ro(self):
        return None if (image := self.__image) is None else True if image is False else not image.flags.writeable

    @property
    def is_rgb(self):
        return None if (shapef := self.__shapef) is None else shapef[1] == 'RGB'

    @property
    def is_bgr(self):
        return None if (shapef := self.__shapef) is None else shapef[1] == 'BGR'

    @property
    def is_gray(self):
        return None if (shapef := self.__shapef) is None else shapef[1] == 'GRAY'

    @property
    def rw(self):
        """If already writable return self. If jpg-only image then decode and return a NEW Frame with a NEW writable
        copy of that image."""

        if (image := self.__image) is None or (image is not False and image.flags.writeable):
            return self

        return Frame(self.image.copy(), self, self.__shapef[1])

    @property
    def ro(self):
        """If already a readonly image or a jpg-only image then return self. Otherwise create a NEW Frame with a
        NEW readonly copy of this writable image."""

        if (image := self.__image) is None or image is False or not image.flags.writeable:
            return self

        new                   = Frame(image := self.image.copy(), self, self.__shapef[1])
        image.flags.writeable = False

        return new

    @property
    def rgb(self):
        """Return self if already RGB (rw or ro) else convert and return converted Frame with same writability. Decodes
        a non-RGB jpg-only Frame to an actual image then converts."""

        if ((shapef := self.__shapef) and shapef[1]) in ('RGB', None):
            return self

        if (image := self.image).flags.writeable:
            new = Frame(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), self, 'RGB')
        elif (new := getattr(self, '_Frame__ro_rgb', None)) is not None:
            return new

        else:
            self.__ro_rgb = new   = Frame(image := cv2.cvtColor(image, cv2.COLOR_RGB2BGR), self, 'RGB')
            image.flags.writeable = False

        return new

    @property
    def bgr(self):
        """Return self if already BGR (rw or ro) else convert and return converted Frame with same writability. Decodes
        a non-BGR jpg-only Frame to an actual image then converts."""

        if ((shapef := self.__shapef) and shapef[1]) in ('BGR', None):
            return self

        if (image := self.image).flags.writeable:
            new = Frame(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), self, 'BGR')
        elif (new := getattr(self, '_Frame__ro_bgr', None)) is not None:
            return new

        else:
            self.__ro_bgr = new   = Frame(image := cv2.cvtColor(image, cv2.COLOR_RGB2BGR), self, 'BGR')
            image.flags.writeable = False

        return new

    @property
    def gray(self):
        """Return self if already GRAY (rw or ro) else convert and return converted Frame with same writability. Decodes
        a non-GRAY jpg-only Frame to an actual image then converts."""

        if ((shapef := self.__shapef) and (format := shapef[1])) in ('GRAY', None):
            return self

        if (image := self.image).flags.writeable:
            new = Frame(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY if format == 'RGB' else cv2.COLOR_BGR2GRAY), self, 'GRAY')
        elif (new := getattr(self, '_Frame__ro_gray', None)) is not None:
            return new

        else:
            self.__ro_gray = new  = Frame(image := cv2.cvtColor(image, cv2.COLOR_RGB2GRAY if format == 'RGB' else cv2.COLOR_BGR2GRAY), self, 'GRAY')
            image.flags.writeable = False

        return new

    @property
    def rw_rgb(self):
        """Return self if already rw RGB else decode / convert / copy and return NEW rw RGB Frame with NEW image."""

        if (shapef := self.__shapef) is None:
            return self
        if shapef[1] == 'RGB':
            return self if (image := self.image).flags.writeable else Frame(image.copy(), self, 'RGB')

        return Frame(cv2.cvtColor(self.image, cv2.COLOR_RGB2BGR), self, 'RGB')

    @property
    def rw_bgr(self):
        """Return self if already rw BGR else decode / convert / copy and return NEW rw BGR Frame with NEW image."""

        if (shapef := self.__shapef) is None:
            return self
        if shapef[1] == 'BGR':
            return self if (image := self.image).flags.writeable else Frame(image.copy(), self, 'BGR')

        return Frame(cv2.cvtColor(self.image, cv2.COLOR_RGB2BGR), self, 'BGR')

    @property
    def ro_rgb(self):
        """Return self if already ro RGB or jpg-only RGB else convert / copy and cache as needed and return NEW ro RGB
        Frame with NEW image."""

        if (shapef := self.__shapef) is None:
            return self

        if shapef[1] == 'RGB':
            if (image := self.__image) is False or not image.flags.writeable:
                return self

            new = Frame(new_image := image.copy(), self, 'RGB')

        elif (new := getattr(self, '_Frame__ro_rgb', None)) is not None:
            return new

        else:
            new           = Frame(new_image := cv2.cvtColor(image := self.image, cv2.COLOR_RGB2BGR), self, 'RGB')
            self.__ro_rgb = new

        new_image.flags.writeable = False

        return new

    @property
    def ro_bgr(self):
        """Return self if already ro BGR or jpg-only BGR else convert / copy and cache as needed and return NEW ro BGR
        Frame with NEW image."""

        if (shapef := self.__shapef) is None:
            return self

        if shapef[1] == 'BGR':
            if (image := self.__image) is False or not image.flags.writeable:
                return self

            new = Frame(new_image := image.copy(), self, 'BGR')

        elif (new := getattr(self, '_Frame__ro_bgr', None)) is not None:
            return new

        else:
            new           = Frame(new_image := cv2.cvtColor(image := self.image, cv2.COLOR_RGB2BGR), self, 'BGR')
            self.__ro_bgr = new

        new_image.flags.writeable = False

        return new

    @property
    def fullstr(self):
        return f'{repr(self)[:-1]}, {self.data})'
