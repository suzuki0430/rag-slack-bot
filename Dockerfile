FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

COPY requirements.txt ./
COPY lambda_function.py ./

RUN pip install -r requirements.txt

CMD ["lambda_function.lambda_handler"]
