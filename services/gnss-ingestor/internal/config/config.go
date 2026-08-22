// Package config loads non-secret ingestor configuration from the environment.
package config

import "os"

type Config struct {
	Address string
}

func Load() Config {
	address := os.Getenv("NLGCP_INGESTOR_ADDRESS")
	if address == "" {
		address = ":8081"
	}
	return Config{Address: address}
}
