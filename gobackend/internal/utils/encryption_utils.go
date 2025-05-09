package utils

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
)

// EncryptKey encrypts a  key using AES-256-GCM.
// This provides authenticated encryption for maximum security.
//
// Parameters:
//   - Key: The plaintext  key to encrypt
//   - encryptionKey: The key to use for encryption (must be at least 32 bytes)
//
// Returns:
//   - The base64-encoded encrypted  key
//   - An error if encryption fails
func EncryptKey(key string, encryptionKey []byte) (string, error) {
	block, err := aes.NewCipher(encryptionKey[:32])
	if err != nil {
		return "", fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("failed to create GCM: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", fmt.Errorf("failed to create nonce: %w", err)
	}

	ciphertext := gcm.Seal(nonce, nonce, []byte(key), nil)

	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

// DecryptKey decrypts a key that was encrypted with EncryptAPIKey.
//
// Parameters:
//   - encryptedKey: The base64-encoded encrypted  key
//   - encryptionKey: The key used for encryption (must be at least 32 bytes)
//
// Returns:
//   - The decrypted plaintext API key
//   - An error if decryption fails
func DecryptKey(encryptedKey string, encryptionKey []byte) (string, error) {
	ciphertext, err := base64.StdEncoding.DecodeString(encryptedKey)
	if err != nil {
		return "", fmt.Errorf("failed to decode base64: %w", err)
	}

	block, err := aes.NewCipher(encryptionKey[:32])
	if err != nil {
		return "", fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("failed to create GCM: %w", err)
	}

	nonceSize := gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return "", errors.New("ciphertext too short")
	}

	nonce, ciphertext := ciphertext[:nonceSize], ciphertext[nonceSize:]

	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", fmt.Errorf("failed to decrypt: %w", err)
	}

	return string(plaintext), nil
}
