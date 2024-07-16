#!/bin/bash

# dstat-interface-cli.sh

set -e

DOCKER_IMAGE_NAME="dstat-interface"
DOCKER_CONTAINER_NAME="dstat-interface-container"

function show_help {
    echo "Usage: $0 [OPTION]"
    echo "Manage dstat-interface Docker container"
    echo ""
    echo "Options:"
    echo "  build    Build the Docker image"
    echo "  run      Run the Docker container"
    echo "  debug    Run the Docker container in interactive mode"
    echo "  stop     Stop the running container"
    echo "  clean    Remove the Docker image and container"
    echo "  help     Show this help message"
}

function build_image {
    echo "Building Docker image..."
    docker build -t $DOCKER_IMAGE_NAME .
}

function run_container {
    echo "Setting up X11 forwarding..."
    xhost + 127.0.0.1

    echo "Running Docker container..."
    docker run -d --name $DOCKER_CONTAINER_NAME \
        -e DISPLAY=host.docker.internal:0 \
        -v /tmp/.X11-unix:/tmp/.X11-unix \
        --rm $DOCKER_IMAGE_NAME

    echo "Container is running. Use 'docker logs $DOCKER_CONTAINER_NAME' to view output."
}

function debug_container {
    echo "Setting up X11 forwarding..."
    xhost + 127.0.0.1

    echo "Running Docker container in interactive mode..."
    docker run -it --name $DOCKER_CONTAINER_NAME \
        -e DISPLAY=host.docker.internal:0 \
        -v /tmp/.X11-unix:/tmp/.X11-unix \
        --rm $DOCKER_IMAGE_NAME /bin/bash
}

function stop_container {
    echo "Stopping Docker container..."
    docker stop $DOCKER_CONTAINER_NAME
}

function clean_up {
    echo "Removing Docker container and image..."
    docker rm -f $DOCKER_CONTAINER_NAME 2>/dev/null || true
    docker rmi -f $DOCKER_IMAGE_NAME 2>/dev/null || true
}

case "$1" in
    build)
        build_image
        ;;
    run)
        run_container
        ;;
    debug)
        debug_container
        ;;
    stop)
        stop_container
        ;;
    clean)
        clean_up
        ;;
    help)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac
