FROM python:3.13-bookworm
WORKDIR /app
COPY . .
RUN python -m unittest -v tests.test_model_curriculum tests.test_model_curriculum_cli
CMD ["python","-c","print('pr192 validation passed')"]
