package orchestrator

import "sync"

type sessionLocker struct {
	mu    sync.Mutex
	locks map[string]*sync.Mutex
}

func newSessionLocker() *sessionLocker {
	return &sessionLocker{
		locks: make(map[string]*sync.Mutex),
	}
}

func (l *sessionLocker) Lock(sessionID string) func() {
	lock := l.get(sessionID)
	lock.Lock()
	return lock.Unlock
}

func (l *sessionLocker) get(sessionID string) *sync.Mutex {
	l.mu.Lock()
	defer l.mu.Unlock()

	lock, ok := l.locks[sessionID]
	if !ok {
		lock = &sync.Mutex{}
		l.locks[sessionID] = lock
	}

	return lock
}
