from enum import Enum


class Direction(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    DOWN_SLIGHT = "down_slight"
