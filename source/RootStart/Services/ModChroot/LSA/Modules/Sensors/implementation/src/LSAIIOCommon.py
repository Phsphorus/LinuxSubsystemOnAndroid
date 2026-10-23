#!/usr/bin/python3

import json
import os


RUNTIME_DIR = os.environ.get(
    "LSA_IIO_RUNTIME",
    "/run/lsa-iio",
)

REGISTRY_PATH = os.environ.get(
    "LSA_IIO_REGISTRY",
    os.path.join(
        RUNTIME_DIR,
        "registry.json",
    ),
)

EVENT_SOCKET = os.path.join(
    RUNTIME_DIR,
    "events.sock",
)

STATE_SOCKET = os.path.join(
    RUNTIME_DIR,
    "state.sock",
)


def load_registry(path=REGISTRY_PATH):
    with open(path) as f:
        registry = json.load(f)

    if int(registry.get("version", 0)) != 1:
        raise RuntimeError(
            "unsupported LSA IIO registry version"
        )

    return registry


def devices_by_role(registry, role):
    return [
        dev
        for dev in registry["devices"]
        if dev.get("role") == role
    ]


def devices_by_kind(registry):
    return {
        dev["kind"]: dev
        for dev in registry["devices"]
    }


def devices_by_dirname(registry):
    return {
        dev["dirname"]: dev
        for dev in registry["devices"]
    }


def event_code(event):
    return (
        (int(event["event_type"]) << 56)
        | (int(event["direction"]) << 48)
        | (int(event["channel_type"]) << 32)
        | int(event.get("channel", 0))
    )
