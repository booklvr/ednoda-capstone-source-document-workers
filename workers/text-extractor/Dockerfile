FROM public.ecr.aws/lambda/python:3.12

COPY text-extractor/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY shared/ ${LAMBDA_TASK_ROOT}/shared/
COPY text-extractor/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY text-extractor/text_cleanup.py ${LAMBDA_TASK_ROOT}/text_cleanup.py
COPY text-extractor/text_blocks.py ${LAMBDA_TASK_ROOT}/text_blocks.py
COPY text-extractor/txt_logic.py ${LAMBDA_TASK_ROOT}/txt_logic.py
COPY text-extractor/pdf_logic.py ${LAMBDA_TASK_ROOT}/pdf_logic.py
COPY text-extractor/csv_logic.py ${LAMBDA_TASK_ROOT}/csv_logic.py
COPY text-extractor/docx_logic.py ${LAMBDA_TASK_ROOT}/docx_logic.py
COPY text-extractor/pptx_logic.py ${LAMBDA_TASK_ROOT}/pptx_logic.py
COPY text-extractor/extraction_limits.py ${LAMBDA_TASK_ROOT}/extraction_limits.py
COPY text-extractor/package_writer.py ${LAMBDA_TASK_ROOT}/package_writer.py

CMD ["handler.handler"]
