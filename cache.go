package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"sync"
)

// Cache provides in-memory storage for parsed metadata indexes and loaded
// skill documents. Entries are invalidated when the source file checksum
// differs from the cached checksum.
type Cache struct {
	mu        sync.RWMutex
	index     []SkillEntry
	indexHash string
	docs      map[string]cachedDoc
}

type cachedDoc struct {
	content  string
	checksum string
}

// NewCache returns an empty ready-to-use cache.
func NewCache() *Cache {
	return &Cache{docs: make(map[string]cachedDoc)}
}

// LoadIndex returns the cached index if it matches the current catalog state.
func (c *Cache) LoadIndex() []SkillEntry {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.index == nil {
		return nil
	}
	return append([]SkillEntry{}, c.index...)
}

// StoreIndex saves an index snapshot keyed by a derived checksum.
func (c *Cache) StoreIndex(index []SkillEntry) {
	h := sha256.New()
	for _, e := range index {
		h.Write([]byte(e.Checksum))
	}
	hash := fmt.Sprintf("%x", h.Sum(nil))

	c.mu.Lock()
	defer c.mu.Unlock()
	c.index = index
	c.indexHash = hash
}

// IndexHash returns the checksum of the currently cached index.
func (c *Cache) IndexHash() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.indexHash
}

// GetDocument returns a cached skill body if it is still valid.
func (c *Cache) GetDocument(path string) (string, bool) {
	c.mu.RLock()
	doc, ok := c.docs[path]
	c.mu.RUnlock()
	if !ok {
		return "", false
	}

	current := fileChecksum(path)
	if current == "" || current != doc.checksum {
		c.mu.Lock()
		delete(c.docs, path)
		c.mu.Unlock()
		return "", false
	}

	return doc.content, true
}

// SetDocument stores a skill body with its current checksum.
func (c *Cache) SetDocument(path, content string) {
	cs := fileChecksum(path)
	c.mu.Lock()
	c.docs[path] = cachedDoc{content: content, checksum: cs}
	c.mu.Unlock()
}

// InvalidateDocument removes a single document from the cache.
func (c *Cache) InvalidateDocument(path string) {
	c.mu.Lock()
	delete(c.docs, path)
	c.mu.Unlock()
}

// InvalidateAll clears the entire cache.
func (c *Cache) InvalidateAll() {
	c.mu.Lock()
	c.index = nil
	c.indexHash = ""
	c.docs = make(map[string]cachedDoc)
	c.mu.Unlock()
}

// DocCount returns the number of cached documents.
func (c *Cache) DocCount() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.docs)
}

func fileChecksum(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return fmt.Sprintf("%x", sha256.Sum256(data))
}
