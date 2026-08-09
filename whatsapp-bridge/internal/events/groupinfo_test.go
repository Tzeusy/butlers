package events_test

import (
	"errors"
	"testing"
	"time"

	waTypes "go.mau.fi/whatsmeow/types"

	"github.com/butlers/whatsapp-bridge/internal/events"
)

type fakeGroupInfoFetcher struct {
	count   int
	err     error
	calls   int
	perCall []struct {
		count int
		err   error
	}
}

func (f *fakeGroupInfoFetcher) ParticipantCount(jid waTypes.JID) (int, error) {
	f.calls++
	if len(f.perCall) > 0 {
		idx := f.calls - 1
		if idx >= len(f.perCall) {
			idx = len(f.perCall) - 1
		}
		return f.perCall[idx].count, f.perCall[idx].err
	}
	return f.count, f.err
}

func mustParseJID(t *testing.T, s string) waTypes.JID {
	t.Helper()
	jid, err := waTypes.ParseJID(s)
	if err != nil {
		t.Fatalf("parse JID %q: %v", s, err)
	}
	return jid
}

func TestGroupInfoCache_CachesWithinTTL(t *testing.T) {
	fetcher := &fakeGroupInfoFetcher{count: 15}
	cache := events.NewGroupInfoCache(fetcher, time.Hour)
	jid := mustParseJID(t, "123456-group@g.us")

	first := cache.ParticipantCount(jid)
	second := cache.ParticipantCount(jid)

	if first != 15 || second != 15 {
		t.Errorf("expected both calls to return 15, got %d and %d", first, second)
	}
	if fetcher.calls != 1 {
		t.Errorf("expected exactly 1 fetch (second call should be a cache hit), got %d", fetcher.calls)
	}
}

func TestGroupInfoCache_RefetchesAfterTTLExpires(t *testing.T) {
	fetcher := &fakeGroupInfoFetcher{count: 15}
	cache := events.NewGroupInfoCache(fetcher, 10*time.Millisecond)
	jid := mustParseJID(t, "123456-group@g.us")

	cache.ParticipantCount(jid)
	time.Sleep(20 * time.Millisecond)
	cache.ParticipantCount(jid)

	if fetcher.calls != 2 {
		t.Errorf("expected 2 fetches after TTL expiry, got %d", fetcher.calls)
	}
}

func TestGroupInfoCache_FetchFailureReturnsZeroAndIsNotCached(t *testing.T) {
	fetcher := &fakeGroupInfoFetcher{
		perCall: []struct {
			count int
			err   error
		}{
			{count: 0, err: errors.New("boom")},
			{count: 20, err: nil},
		},
	}
	cache := events.NewGroupInfoCache(fetcher, time.Hour)
	jid := mustParseJID(t, "123456-group@g.us")

	failed := cache.ParticipantCount(jid)
	if failed != 0 {
		t.Errorf("expected 0 on fetch failure, got %d", failed)
	}

	// A fetch failure must not be cached — the very next call should retry,
	// not silently return a wedged "unknown" for the full TTL.
	retried := cache.ParticipantCount(jid)
	if retried != 20 {
		t.Errorf("expected retry to succeed with 20, got %d", retried)
	}
	if fetcher.calls != 2 {
		t.Errorf("expected 2 fetch attempts (no caching of the failure), got %d", fetcher.calls)
	}
}

func TestGroupInfoCache_DifferentJIDsCachedIndependently(t *testing.T) {
	fetcher := &fakeGroupInfoFetcher{
		perCall: []struct {
			count int
			err   error
		}{
			{count: 5, err: nil},
			{count: 300, err: nil},
		},
	}
	cache := events.NewGroupInfoCache(fetcher, time.Hour)
	jidA := mustParseJID(t, "111-group@g.us")
	jidB := mustParseJID(t, "222-group@g.us")

	countA := cache.ParticipantCount(jidA)
	countB := cache.ParticipantCount(jidB)

	if countA != 5 {
		t.Errorf("group A: got %d want 5", countA)
	}
	if countB != 300 {
		t.Errorf("group B: got %d want 300", countB)
	}
	if fetcher.calls != 2 {
		t.Errorf("expected 2 fetches for 2 distinct groups, got %d", fetcher.calls)
	}
}
