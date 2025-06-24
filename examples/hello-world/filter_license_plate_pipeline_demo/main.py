from openfilter.filter_runtime.filter import Filter
from filter_license_plate_detection.filter import FilterLicensePlateDetection
from filter_crop.filter import FilterCrop
from filter_optical_character_recognition.filter import FilterOpticalCharacterRecognition
from filter_license_annotation_demo.filter import FilterLicenseAnnotationDemo
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis


if __name__ == '__main__':
    Filter.run_multi([
        (VideoIn, dict(
            sources='file://example_video.mp4!loop',
           
            outputs='tcp://*:5550',
        )),
        (FilterLicensePlateDetection, dict(
            sources='tcp://localhost:5550',
            outputs='tcp://*:5552',
        )),
        (FilterCrop, dict( 
            sources='tcp://localhost:5552',
            outputs='tcp://*:5554',
            detection_key='license_plate_detection',
            detection_class_field='label',
            detection_roi_field='box',
            output_prefix='cropped_',
            mutate_original_frames=False,
            topic_mode='main_only',
        )),
        (FilterOpticalCharacterRecognition, dict( 
            sources='tcp://localhost:5554',
            outputs='tcp://*:5556',
            topic_pattern='license_plate',
            ocr_engine='easyocr',
            forward_ocr_texts=True,
        )),
        (FilterLicenseAnnotationDemo, dict( 
            sources='tcp://localhost:5556',
            outputs='tcp://*:5558',
            cropped_topic_suffix='license_plate',
        )),
        (Webvis, dict(
            sources='tcp://localhost:5558',
        )),
    ])