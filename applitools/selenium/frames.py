import copy

import typing as tp

from applitools.core import Point, EyesError

if tp.TYPE_CHECKING:
    from applitools.utils.custom_types import FrameReference

__all__ = ('EyesFrame', 'FrameChain')


class EyesFrame(object):
    """
    Encapsulates data about frames.
    """
    __slots__ = ('reference', 'location', 'size', 'id', 'parent_scroll_position')

    def __init__(self, reference, location, size, id_, parent_scroll_position):
        # type: (FrameReference, tp.Dict, tp.Dict, int, Point) -> None
        """
        Ctor.

        :param reference: The reference to the frame.
        :param location: The location of the frame.
        :param size: The size of the frame.
        :param id_: The id of the frame.
        :param parent_scroll_position: The parents' scroll position.
        """
        self.reference = reference
        self.location = location
        self.size = size
        self.id = id_
        self.parent_scroll_position = parent_scroll_position

    def __str__(self):
        return "EyesFrame: {}".format(self.reference)

    def __len__(self):
        return self.size


class FrameChain(tp.Sequence[EyesFrame]):
    __slots__ = ('_frames',)

    def __init__(self, frame_chain=None):
        self._frames = []
        if frame_chain is not None:
            assert isinstance(frame_chain, FrameChain), 'Must be a FrameChain'
            self._frames = copy.deepcopy(frame_chain)

    def __iter__(self):
        return iter(self._frames)

    def __getitem__(self, item):
        return self._frames[item]

    def __len__(self):
        return len(self._frames)

    def __repr__(self):
        return 'FrameChain with {} frames'.format(len(self))

    def __eq__(self, other):
        return set(self) == set(other)

    def clear(self):
        self._frames = []

    @property
    def peek(self):
        # type: () -> EyesFrame
        return self[-1]

    def append(self, frame):
        assert isinstance(frame, EyesFrame), 'frame must be instance of EyesFrame!'
        self._frames.append(frame)

    def pop(self):
        self._frames.pop()

    @property
    def current_frame_offset(self):
        # type: () -> Point
        location = Point.create_top_left()
        for frame in self:
            location.offset_by_location(frame.location)
        return location

    @property
    def current_frame_size(self):
        # type: () -> int
        return len(self.peek)

    @property
    def default_content_scroll_position(self):
        # type: () -> tp.Union[Point, EyesError]
        if len(self) == 0:
            raise EyesError('No frames in frame chain')
        result = self[0].parent_scroll_position
        return Point(result.x, result.y)
