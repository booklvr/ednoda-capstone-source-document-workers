# Reconciled with Nick's integrated Dockerfile (CPU-only PyTorch + a baked
# Hugging Face model snapshot + an offline build-time KeyBERT load check) so the
# image does not download models at runtime. Build context is the `workers/`
# directory (so `shared/` and `candidate-extractor-nlu/` are both visible).
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu

COPY candidate-extractor-nlu/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN python -m spacy download en_core_web_sm
RUN mkdir -p /opt/models /tmp/huggingface /tmp/sentence-transformers \
  && HOME=/tmp HF_HOME=/tmp/huggingface SENTENCE_TRANSFORMERS_HOME=/tmp/sentence-transformers python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='sentence-transformers/all-MiniLM-L6-v2', local_dir='/opt/models/all-MiniLM-L6-v2', local_dir_use_symlinks=False)" \
  && HOME=/tmp HF_HOME=/tmp/huggingface SENTENCE_TRANSFORMERS_HOME=/tmp/sentence-transformers TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python -c "from keybert import KeyBERT; KeyBERT('/opt/models/all-MiniLM-L6-v2')"

ENV HOME=/tmp
ENV HF_HOME=/tmp/huggingface
ENV HF_HUB_CACHE=/tmp/huggingface/hub
ENV TRANSFORMERS_CACHE=/tmp/huggingface/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/tmp/sentence-transformers
ENV MPLCONFIGDIR=/tmp/matplotlib
ENV TOKENIZERS_PARALLELISM=false
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
# Point the labeller at the baked model PATH. Required because the runtime is
# offline (HF_HUB_OFFLINE=1) and the model lives at a local_dir, not in the HF
# cache — loading by name ("all-MiniLM-L6-v2") would fail. Ednoda may override.
ENV KEYBERT_MODEL=/opt/models/all-MiniLM-L6-v2

COPY shared/ ${LAMBDA_TASK_ROOT}/shared/
COPY candidate-extractor-nlu/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY candidate-extractor-nlu/chunker.py ${LAMBDA_TASK_ROOT}/chunker.py
COPY candidate-extractor-nlu/cleaner.py ${LAMBDA_TASK_ROOT}/cleaner.py
COPY candidate-extractor-nlu/labeller.py ${LAMBDA_TASK_ROOT}/labeller.py
# A-E hardening modules (not in Nick's snapshot — added by us). Required at
# runtime: handler imports preprocess/chunk_dedup/candidate_pruner; preprocess
# and labeller import language_filter.
COPY candidate-extractor-nlu/language_filter.py ${LAMBDA_TASK_ROOT}/language_filter.py
COPY candidate-extractor-nlu/preprocess.py ${LAMBDA_TASK_ROOT}/preprocess.py
COPY candidate-extractor-nlu/chunk_dedup.py ${LAMBDA_TASK_ROOT}/chunk_dedup.py
COPY candidate-extractor-nlu/candidate_pruner.py ${LAMBDA_TASK_ROOT}/candidate_pruner.py
COPY candidate-extractor-nlu/data/ ${LAMBDA_TASK_ROOT}/data/

CMD ["handler.handler"]
