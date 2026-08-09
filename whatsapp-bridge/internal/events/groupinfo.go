package events

import (
	"sync"
	"time"

	waTypes "go.mau.fi/whatsmeow/types"
)

// GroupInfoFetcher resolves a group's live participant count, e.g. via
// whatsmeow's Client.GetGroupInfo. Abstracted as an interface so
// GroupInfoCache is unit-testable without a live WhatsApp connection.
type GroupInfoFetcher interface {
	ParticipantCount(jid waTypes.JID) (int, error)
}

type groupCacheEntry struct {
	count   int
	expires time.Time
}

// GroupInfoCache resolves and caches WhatsApp group participant counts with
// a TTL, so an active group doesn't trigger a GetGroupInfo network round
// trip (a request to WhatsApp's servers) on every single message.
type GroupInfoCache struct {
	fetcher GroupInfoFetcher
	ttl     time.Duration

	mu      sync.Mutex
	entries map[string]groupCacheEntry
}

// NewGroupInfoCache constructs a cache backed by fetcher with the given TTL.
func NewGroupInfoCache(fetcher GroupInfoFetcher, ttl time.Duration) *GroupInfoCache {
	return &GroupInfoCache{
		fetcher: fetcher,
		ttl:     ttl,
		entries: make(map[string]groupCacheEntry),
	}
}

// ParticipantCount returns the cached or freshly-fetched participant count
// for jid. Returns 0 (unknown) on fetch failure — this is best-effort and
// must never block or fail the message pipeline; callers should treat 0 as
// "omit the field", never as a real group size of zero.
//
// A fetch failure is NOT cached, so a transient error (e.g. a momentary
// disconnect) doesn't wedge the group at "unknown" for the full TTL — the
// next message retries.
func (c *GroupInfoCache) ParticipantCount(jid waTypes.JID) int {
	key := jid.String()

	c.mu.Lock()
	entry, ok := c.entries[key]
	c.mu.Unlock()
	if ok && time.Now().Before(entry.expires) {
		return entry.count
	}

	count, err := c.fetcher.ParticipantCount(jid)
	if err != nil {
		return 0
	}

	c.mu.Lock()
	c.entries[key] = groupCacheEntry{count: count, expires: time.Now().Add(c.ttl)}
	c.mu.Unlock()
	return count
}
