"""
read and write document and image data
"""

from ..HttpRouter import ResponseFail
from .route import route, router
from typing import Any, Tuple
from krita import *
from ..utils import *
from datetime import datetime
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from ..PerWindowCachedState import PerWindowCachedState
from ..Logger import Logger

logger = Logger()

@route('document/layers')
def get_layers(_, ok, fail):
    doc = active_document()
    if doc is None:
        return fail("No active document", None)
    doc.node
    pass

@route('document/open', {
    'path': str
})
def open_new_image(req):
    doc = Krita.instance().openDocument(req['path'])
    active_window().addView(doc)
    return 'done'


@route('document/convert_to_open', {
    'original_path': str,
    'target_path': str,
})
def export(req):
    doc = Krita.instance().openDocument(req['original_path'])
    doc.saveAs(req['target_path'])
    active_window().addView(doc)
    return 'done'

# class GetImageThread(QThread):
#     request_image = pyqtSignal()
#     image_ready = pyqtSignal()
#     def __init__(self):
#         super().__init__()
#         self.base64 = None

#     def run(self) -> None:
#         # Wait for the result to be set by the main thread
#         with open('D:/hello.bin', 'wb') as f:
#             while True:
#                 try:
#                     self.__go(f)
#                 except BaseException as e:
#                     logger.warn('error happened in GetImage Thread. ')
#                     logger.warn(str(e))
            
#     def __go(self, f):
#         loop = QEventLoop()
#         self.request_image.connect(loop.quit)
#         loop.exec()
#         logger.info('start get image')
#         doc = active_document() # won't fail
#         logger.info('get document done')
#         w = doc.width()
#         h = doc.height()
#         image_bytes = doc.pixelData(0, 0, w, h) # Blue, Green, Red, Alpha
#         logger.info('get bytes done')
#         f.write(image_bytes)
#         logger.info('write bytes done')
#         self.image_ready.emit()

# __get_image_thread = None

# @route('document/image')
# def get_image(_, ok: Callable[[Any], None], fail: Callable[[str, Any], None]):
#     if not Krita.instance().action('recorder_record_toggle').isChecked:
#         return fail('not recording.', None)
    
#     doc = active_document()
#     if doc is None:
#         return fail("No active document", None)
#     # if doc.colorDepth() != 'U8' or doc.colorModel() != 'RGBA':
#     #     return fail(f"Only RGBA 8-bit is supported, got {doc.colorModel} {doc.colorDepth}", None)
#     w = doc.width()
#     h = doc.height()
#     depth = doc.colorDepth()
#     model = doc.colorModel()


#     pass
    # global __get_image_thread
    # if __get_image_thread is None:
    #     __get_image_thread = GetImageThread()
    #     __get_image_thread.start()
    # doc = active_document()
    # if doc is None:
    #     return fail("No active document", None)
    # # if doc.colorDepth() != 'U8' or doc.colorModel() != 'RGBA':
    # #     return fail(f"Only RGBA 8-bit is supported, got {doc.colorModel} {doc.colorDepth}", None)
    # w = doc.width()
    # h = doc.height()
    # depth = doc.colorDepth()
    # model = doc.colorModel()
    
    # # p0 = datetime.now().timestamp()
    # # with open('D:/hello.bin', 'wb') as f:
    # #     f.write(doc.pixelData(0, 0, w, h))
    # # # base64 = str(image_bytes.toBase64(), 'utf-8')
    # # p1 = datetime.now().timestamp()
    # # return ok({
    # #     'w': w, 'h': h, 'depth': depth, 'model': model, 
    # #     # 'image': base64, 
    # #     'cost': int((p1 - p0) * 1000), 
    # # })

    # pixel_data_start = datetime.now().timestamp()
    # __get_image_thread.request_image.emit()
    # def go():
    #     __get_image_thread.image_ready.disconnect(go)
    #     pixel_data_end = datetime.now().timestamp()
    #     logger.info('callback')
    #     return ok({
    #         'w': w, 'h': h, 'depth': depth, 'model': model, 
    #         'cost': int((pixel_data_end - pixel_data_start) * 1000), 
    #     })
    # __get_image_thread.image_ready.connect(go)


# useless...
@route('document/image', {
    'withImage': bool
})
def get_image(req, ok: Callable[[Any], None], fail: Callable[[str, Any], None]):
    doc = active_document()
    if doc is None:
        return fail("No active document", None)
    # if doc.colorDepth() != 'U8' or doc.colorModel() != 'RGBA':
    #     return fail(f"Only RGBA 8-bit is supported, got {doc.colorModel} {doc.colorDepth}", None)
    w = doc.width()
    h = doc.height()
    depth = doc.colorDepth()
    model = doc.colorModel()

    a = datetime.now().timestamp()
    pixel_data = doc.pixelData(0, 0, w, h)
    b = datetime.now().timestamp()
    base64=str(pixel_data.toBase64(), 'utf-8')
    c = datetime.now().timestamp()
    res = dict(
        w=w,h=h,depth=depth,model=model,getPixelBytesCost=round((b-a) * 1000),getBase64Cost=round((c-b) * 1000)
    )
    if req['withImage']:
        res['base64']=base64
    ok(res)
    

def __get_record_dir(window: Window):
    recorder_docker = next((i for i in window.dockers() if i.objectName() == 'RecorderDocker'))
    dir_obj = recorder_docker.findChild(QLineEdit,'editDirectory')
    return dir_obj

__recorder_dir_widget = PerWindowCachedState(__get_record_dir)


@route('document/records')
def image_path(_,ok,fail):
    doc = active_document()
    if doc is None:
        return fail("No active document", None)
    
    if not Krita.instance().action('recorder_record_toggle').isChecked:
        return fail('not recording.', None)
    
    dir_obj = __recorder_dir_widget.get(Krita.instance().activeWindow())
    record_directory = dir_obj.text()

    # if doc.colorDepth() != 'U8' or doc.colorModel() != 'RGBA':
    #     return fail(f"Only RGBA 8-bit is supported, got {doc.colorModel} {doc.colorDepth}", None)
    w = doc.width()
    h = doc.height()
    depth = doc.colorDepth()
    model = doc.colorModel()
    formatted_date = DocumentInfo.from_document(doc).create_date.strftime('%Y%m%d%H%M%S')
    doc_record_path = os.path.join(record_directory,formatted_date).replace('\\', '/')
    
    if not os.path.exists(doc_record_path):
        return fail('No record yet.', None)
    
    return ok(dict(
        w=w,h=h,depth=depth,model=model,path=doc_record_path,records=os.listdir(doc_record_path)
    ))