from e1r_decoder.frame import FrameAssembler, SplitStrategyBySeq
from e1r_decoder.msop import decode_msop

def assemble(seqs, factory):
    assembler = FrameAssembler()
    frames = []
    for seq in seqs:
        f = assembler.push(decode_msop(factory(seq=seq)))
        if f is not None:
            frames.append(f)
    f = assembler.flush()
    if f is not None:
        frames.append(f)
    return frames, assembler.stats

def test_normal_partial(packet_factory):
    frames, _ = assemble(list(range(1, 30))*3, packet_factory)
    assert [f.complete for f in frames] == [False, True, False]
    assert all(f.packet_count == 29 for f in frames)

def test_midframe(packet_factory):
    frames, _ = assemble(list(range(14, 30))+[1], packet_factory)
    assert not frames[0].complete
    assert "capture_start_unverified" in frames[0].reasons

def test_drop_duplicate_disorder(packet_factory):
    middle = list(range(1, 30))
    middle.remove(7)
    middle.insert(8, middle[7])
    middle[13], middle[14] = middle[14], middle[13]
    frames, stats = assemble(list(range(1,30))+middle+[1], packet_factory)
    assert not frames[1].complete
    assert stats["duplicates"] == 1
    assert stats["sequence_gaps"] > 0 and stats["order_anomalies"] == 1
    assert frames[1].packet_count == len(middle)

def test_uint16_wrap():
    s = SplitStrategyBySeq()
    assert not s.push(65530)
    assert not s.push(65535)
    assert s.push(0)

def test_large_forward_jump_matches_official():
    s = SplitStrategyBySeq()
    s.push(20)
    assert not s.push(50)
    assert s.prev == 20
    assert not s.push(12)
    assert s.push(1)

def test_tail_drop_after_observed_extent(packet_factory):
    frames, _ = assemble(list(range(1,30))+list(range(1,27))+[1], packet_factory)
    assert not frames[1].complete
    assert "end_sequence_shorter_than_observed" in frames[1].reasons
