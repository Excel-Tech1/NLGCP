package ntrip

import (
	"crypto/sha256"
	"fmt"
)

// ConfigError reports an invalid ingestion configuration value.
type ConfigError struct {
	Field string
}

func (e *ConfigError) Error() string { return "invalid ntrip config: " + e.Field }

// SHA256Sum returns the SHA-256 digest of data.
func SHA256Sum(data []byte) [32]byte { return sha256.Sum256(data) }

// SHA256Hex returns the lowercase hex SHA-256 digest of data.
func SHA256Hex(data []byte) string { return fmt.Sprintf("%x", SHA256Sum(data)) }

// itoa renders small finding strings without fmt overhead in hot paths.
func itoa(prefix string, value int64, length int) string {
	if length > 0 {
		return fmt.Sprintf("%s%d length=%d", prefix, value, length)
	}
	return fmt.Sprintf("%s%d", prefix, value)
}
