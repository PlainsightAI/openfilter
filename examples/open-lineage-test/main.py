from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis

videopath = "/home/tales/filter-examples/license_plate_example/license_plate_filter/assets/videos/video2.mp4"
if __name__ == '__main__':
    Filter.run_multi([
        (VideoIn, dict(
            #sources='file://example_video.mp4!loop',
            sources=f"file://{videopath}",
            outputs='tcp://*:5550',
        )),
        (Webvis, dict(
            sources='tcp://localhost:5550',
        )),
    ])