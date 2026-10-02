from django.core.files.uploadhandler import FileUploadHandler, StopUpload

from pipeline.source_parser import MAX_BYTES


class BoundedUploadHandler(FileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > MAX_BYTES:
            self.request.upload_too_large = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None
