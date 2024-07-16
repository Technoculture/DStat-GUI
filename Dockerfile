# Use a base image with Python 2.7
FROM python:2.7-slim-buster

# Install system dependencies
RUN apt-get update && apt-get install -y \
  python-gtk2 \
  python-cairo \
  libzmq3-dev \
  libfreetype6-dev \
  libpng-dev \
  pkg-config \
  && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install setup tools
RUN pip install --no-cache-dir --upgrade pip==20.3.4 setuptools==44.1.1

# Install Python dependencies with specific versions
RUN pip install --no-cache-dir \
  numpy==1.9.2 \
  pyserial==2.7 \
  pyzmq==14.6.0

# Install matplotlib separately
RUN pip install --no-cache-dir matplotlib==1.4.3

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Run main.py when the container launches
CMD ["python", "main.py"]
