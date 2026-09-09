package ntrip

// BoundedBuffer is a fixed-capacity queue with explicit backpressure:
// BLOCK waits (counted) while DROP_NEWEST_EXPLICIT counts drops.
// There is no silent-discard path.
type BackpressurePolicy int

const (
	// BlockBackpressure waits for capacity (counted waits, no loss).
	BlockBackpressure BackpressurePolicy = iota
	// DropNewestExplicit drops the newest item with a counted drop.
	DropNewestExplicit
)

// BoundedBuffer records occupancy, high-water mark, waits, and drops.
type BoundedBuffer[T any] struct {
	capacity  int
	policy    BackpressurePolicy
	queue     []T
	HighWater int
	Dropped   int
	Waits     int
	MaxDepth  int
}

// NewBoundedBuffer returns a buffer with the given capacity (>= 1).
func NewBoundedBuffer[T any](capacity int, policy BackpressurePolicy) (*BoundedBuffer[T], error) {
	if capacity < 1 {
		return nil, &ConfigError{Field: "buffer_capacity"}
	}
	return &BoundedBuffer[T]{capacity: capacity, policy: policy}, nil
}

// Capacity returns the configured capacity.
func (b *BoundedBuffer[T]) Capacity() int { return b.capacity }

// Occupancy returns the current queue depth.
func (b *BoundedBuffer[T]) Occupancy() int { return len(b.queue) }

// TryPut inserts without blocking; false means full (wait or drop counted).
func (b *BoundedBuffer[T]) TryPut(item T) bool {
	if len(b.queue) >= b.capacity {
		if b.policy == DropNewestExplicit {
			b.Dropped++
			return false
		}
		b.Waits++
		return false
	}
	b.queue = append(b.queue, item)
	b.observe()
	return true
}

// ForcePut inserts after the caller drained capacity (else it panics).
func (b *BoundedBuffer[T]) ForcePut(item T) {
	if len(b.queue) >= b.capacity {
		panic("buffer full: ForcePut requires occupancy < capacity")
	}
	b.queue = append(b.queue, item)
	b.observe()
}

// Take removes the oldest item, or false when empty.
func (b *BoundedBuffer[T]) Take() (T, bool) {
	var zero T
	if len(b.queue) == 0 {
		return zero, false
	}
	item := b.queue[0]
	b.queue = b.queue[1:]
	return item, true
}

func (b *BoundedBuffer[T]) observe() {
	if len(b.queue) > b.HighWater {
		b.HighWater = len(b.queue)
	}
	if len(b.queue) > b.MaxDepth {
		b.MaxDepth = len(b.queue)
	}
}
