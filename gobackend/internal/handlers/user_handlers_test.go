package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// MockUserService is a mock implementation of the UserService
type MockUserService struct {
	mock.Mock
}

func (m *MockUserService) GetUserByID(ctx context.Context, id int64) (*models.User, error) {
	args := m.Called(ctx, id)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.User), args.Error(1)
}

func (m *MockUserService) UpdateUser(ctx context.Context, id int64, update *models.UserUpdate) (*models.User, error) {
	args := m.Called(ctx, id, update)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.User), args.Error(1)
}

func (m *MockUserService) ChangePassword(ctx context.Context, id int64, currentPassword, newPassword string) error {
	args := m.Called(ctx, id, currentPassword, newPassword)
	return args.Error(0)
}

func (m *MockUserService) DeleteUser(ctx context.Context, id int64) error {
	args := m.Called(ctx, id)
	return args.Error(0)
}

func (m *MockUserService) CheckUsername(ctx context.Context, username string) (bool, error) {
	args := m.Called(ctx, username)
	return args.Bool(0), args.Error(1)
}

func (m *MockUserService) CheckEmail(ctx context.Context, email string) (bool, error) {
	args := m.Called(ctx, email)
	return args.Bool(0), args.Error(1)
}

func (m *MockUserService) GetUserActiveSessions(ctx context.Context, userID int64) ([]*models.ActiveSessionInfo, error) {
	args := m.Called(ctx, userID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]*models.ActiveSessionInfo), args.Error(1)
}

func (m *MockUserService) InvalidateSession(ctx context.Context, userID int64, sessionID string) error {
	args := m.Called(ctx, userID, sessionID)
	return args.Error(0)
}

// Helper functions for testing
func setupUserTest(t *testing.T) (*UserHandler, *MockUserService) {
	mockService := new(MockUserService)
	handler := NewUserHandler(mockService)
	return handler, mockService
}

func createAuthContext(userID int64) context.Context {
	ctx := context.Background()
	return context.WithValue(ctx, auth.UserIDContextKey, userID)
}

// Helper function to get a consistent time for testing
func testTime() time.Time {
	return time.Date(2023, 1, 1, 12, 0, 0, 0, time.UTC)
}

// TestGetCurrentUser tests the GetCurrentUser handler
func TestGetCurrentUser(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Success", func(t *testing.T) {
		// Create expected user with consistent time values
		expectedUser := &models.User{
			ID:        1001,
			Username:  "testuser",
			Email:     "test@example.com",
			CreatedAt: testTime(),
			UpdatedAt: testTime(),
		}

		// Setup mock service
		mockService.On("GetUserByID", mock.Anything, int64(1001)).Return(expectedUser, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/users/me", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetCurrentUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool        `json:"success"`
			Data    models.User `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedUser.ID, responseWrapper.Data.ID)
		assert.Equal(t, expectedUser.Username, responseWrapper.Data.Username)
		assert.Equal(t, expectedUser.Email, responseWrapper.Data.Email)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("GET", "/api/users/me", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetCurrentUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "unauthorized", responseWrapper.Error.Code)
		assert.Equal(t, "Authentication required", responseWrapper.Error.Message)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("GetUserByID", mock.Anything, int64(1001)).Return(nil, errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/users/me", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetCurrentUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Not Found Error", func(t *testing.T) {
		// Setup mock service to return not found error
		mockService.On("GetUserByID", mock.Anything, int64(1001)).Return(nil, utils.NewNotFoundError("User", 1001)).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/users/me", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetCurrentUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusNotFound, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "not_found", responseWrapper.Error.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// TestUpdateUser tests the UpdateUser handler
func TestUpdateUser(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Success", func(t *testing.T) {
		// Create request payload
		update := models.UserUpdate{
			Username: "updateduser",
			Email:    "updated@example.com",
		}

		// Expected updated user with consistent time values
		expectedUser := &models.User{
			ID:        1001,
			Username:  "updateduser",
			Email:     "updated@example.com",
			CreatedAt: testTime(),
			UpdatedAt: testTime(),
		}

		// Setup mock service
		mockService.On("UpdateUser", mock.Anything, int64(1001), mock.MatchedBy(func(u *models.UserUpdate) bool {
			return u.Username == update.Username && u.Email == update.Email
		})).Return(expectedUser, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool        `json:"success"`
			Data    models.User `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedUser.ID, responseWrapper.Data.ID)
		assert.Equal(t, expectedUser.Username, responseWrapper.Data.Username)
		assert.Equal(t, expectedUser.Email, responseWrapper.Data.Email)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"username": invalid}`)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/users/me", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		update := models.UserUpdate{
			Username: "updateduser",
		}
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("PUT", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Duplicate Username", func(t *testing.T) {
		// Create request payload
		update := models.UserUpdate{
			Username: "existinguser",
		}

		// Setup mock service to return duplicate error
		mockService.On("UpdateUser", mock.Anything, int64(1001), mock.MatchedBy(func(u *models.UserUpdate) bool {
			return u.Username == update.Username
		})).Return(nil, utils.NewDuplicateError("User", "username", update.Username)).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusConflict, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "duplicate_resource", responseWrapper.Error.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		update := models.UserUpdate{
			Username: "updateduser",
		}

		// Setup mock service to return error
		mockService.On("UpdateUser", mock.Anything, int64(1001), mock.MatchedBy(func(u *models.UserUpdate) bool {
			return u.Username == update.Username
		})).Return(nil, errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateUser(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// TestChangePassword tests the ChangePassword handler
func TestChangePassword(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Success", func(t *testing.T) {
		// Create request payload
		req := struct {
			CurrentPassword string `json:"current_password"`
			NewPassword     string `json:"new_password"`
			ConfirmPassword string `json:"confirm_password"`
		}{
			CurrentPassword: "oldpassword",
			NewPassword:     "newpassword123",
			ConfirmPassword: "newpassword123",
		}

		// Setup mock service
		mockService.On("ChangePassword", mock.Anything, int64(1001), req.CurrentPassword, req.NewPassword).Return(nil).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("POST", "/api/users/me/change-password", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.ChangePassword(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Message string `json:"message"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "Password successfully changed", responseWrapper.Data.Message)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Password Mismatch", func(t *testing.T) {
		// Create request payload with mismatched passwords
		req := struct {
			CurrentPassword string `json:"current_password"`
			NewPassword     string `json:"new_password"`
			ConfirmPassword string `json:"confirm_password"`
		}{
			CurrentPassword: "oldpassword",
			NewPassword:     "newpassword123",
			ConfirmPassword: "differentpassword",
		}

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("POST", "/api/users/me/change-password", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.ChangePassword(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "validation_error", responseWrapper.Error.Code)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"current_password": invalid}`)

		// Create test request
		httpReq, err := http.NewRequest("POST", "/api/users/me/change-password", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.ChangePassword(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		req := struct {
			CurrentPassword string `json:"current_password"`
			NewPassword     string `json:"new_password"`
			ConfirmPassword string `json:"confirm_password"`
		}{
			CurrentPassword: "oldpassword",
			NewPassword:     "newpassword123",
			ConfirmPassword: "newpassword123",
		}
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request without auth context
		httpReq, err := http.NewRequest("POST", "/api/users/me/change-password", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.ChangePassword(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		req := struct {
			CurrentPassword string `json:"current_password"`
			NewPassword     string `json:"new_password"`
			ConfirmPassword string `json:"confirm_password"`
		}{
			CurrentPassword: "oldpassword",
			NewPassword:     "newpassword123",
			ConfirmPassword: "newpassword123",
		}

		// Setup mock service to return error
		mockService.On("ChangePassword", mock.Anything, int64(1001), req.CurrentPassword, req.NewPassword).Return(errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("POST", "/api/users/me/change-password", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.ChangePassword(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// TestDeleteAccount tests the DeleteAccount handler
func TestDeleteAccount(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Success", func(t *testing.T) {
		// Create request payload
		req := struct {
			Password string `json:"password"`
			Confirm  string `json:"confirm"`
		}{
			Password: "password123",
			Confirm:  "DELETE",
		}

		// Setup mock service
		mockService.On("DeleteUser", mock.Anything, int64(1001)).Return(nil).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.DeleteAccount(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Message string `json:"message"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "Account successfully deleted", responseWrapper.Data.Message)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Confirmation", func(t *testing.T) {
		// Create request payload with wrong confirmation text
		req := struct {
			Password string `json:"password"`
			Confirm  string `json:"confirm"`
		}{
			Password: "password123",
			Confirm:  "Wrong", // Should be "DELETE"
		}

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.DeleteAccount(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "validation_error", responseWrapper.Error.Code)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"password": invalid}`)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.DeleteAccount(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		req := struct {
			Password string `json:"password"`
			Confirm  string `json:"confirm"`
		}{
			Password: "password123",
			Confirm:  "DELETE",
		}
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request without auth context
		httpReq, err := http.NewRequest("DELETE", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.DeleteAccount(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		req := struct {
			Password string `json:"password"`
			Confirm  string `json:"confirm"`
		}{
			Password: "password123",
			Confirm:  "DELETE",
		}

		// Setup mock service to return error
		mockService.On("DeleteUser", mock.Anything, int64(1001)).Return(errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.DeleteAccount(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// TestCheckUsername tests the CheckUsername handler
func TestCheckUsername(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Username Available", func(t *testing.T) {
		// Setup mock service
		mockService.On("CheckUsername", mock.Anything, "newuser").Return(true, nil).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/username?username=newuser", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckUsername(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Username  string `json:"username"`
				Available bool   `json:"available"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "newuser", responseWrapper.Data.Username)
		assert.True(t, responseWrapper.Data.Available)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Username Not Available", func(t *testing.T) {
		// Setup mock service
		mockService.On("CheckUsername", mock.Anything, "existinguser").Return(false, nil).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/username?username=existinguser", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckUsername(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Username  string `json:"username"`
				Available bool   `json:"available"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "existinguser", responseWrapper.Data.Username)
		assert.False(t, responseWrapper.Data.Available)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Missing Username Parameter", func(t *testing.T) {
		// Create test request without query parameter
		req, err := http.NewRequest("GET", "/api/users/check/username", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckUsername(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "bad_request", responseWrapper.Error.Code)
		assert.Equal(t, "Username parameter is required", responseWrapper.Error.Message)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("CheckUsername", mock.Anything, "testuser").Return(false, errors.New("service error")).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/username?username=testuser", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckUsername(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Validation Error", func(t *testing.T) {
		// Setup mock service to return validation error
		validationErr := utils.NewValidationError("username", "Invalid username format")
		mockService.On("CheckUsername", mock.Anything, "invalid@user").Return(false, validationErr).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/username?username=invalid@user", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckUsername(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "validation_error", responseWrapper.Error.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// TestCheckEmail tests the CheckEmail handler
func TestCheckEmail(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Email Available", func(t *testing.T) {
		// Setup mock service
		mockService.On("CheckEmail", mock.Anything, "new@example.com").Return(true, nil).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/email?email=new@example.com", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckEmail(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Email     string `json:"email"`
				Available bool   `json:"available"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "new@example.com", responseWrapper.Data.Email)
		assert.True(t, responseWrapper.Data.Available)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Email Not Available", func(t *testing.T) {
		// Setup mock service
		mockService.On("CheckEmail", mock.Anything, "existing@example.com").Return(false, nil).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/email?email=existing@example.com", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckEmail(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Email     string `json:"email"`
				Available bool   `json:"available"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "existing@example.com", responseWrapper.Data.Email)
		assert.False(t, responseWrapper.Data.Available)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Missing Email Parameter", func(t *testing.T) {
		// Create test request without query parameter
		req, err := http.NewRequest("GET", "/api/users/check/email", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckEmail(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "bad_request", responseWrapper.Error.Code)
		assert.Equal(t, "Email parameter is required", responseWrapper.Error.Message)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("CheckEmail", mock.Anything, "test@example.com").Return(false, errors.New("service error")).Once()

		// Create test request with query parameter
		req, err := http.NewRequest("GET", "/api/users/check/email?email=test@example.com", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CheckEmail(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	/*
		t.Run("Validation Error", func(t *testing.T) {
			// Setup mock service to return validation error
			validationErr := utils.NewValidationError("email", "Invalid email format")
			mockService.On("CheckEmail", mock.Anything, "invalid-email").Return(false, validationErr).Once()

			// Create test request with query parameter
			req, err := http.NewRequest("GET", "/api/users/check/email?email=invalid-email", nil)
			require.NoError(t, err)

			// Create response recorder
			rr := httptest.NewRecorder()

			// Call the handler
			handler.CheckEmail(rr, req)

			// Verify response
			assert.Equal(t, http.StatusBadRequest, rr.Code)

			// Define wrapper for the error response envelope
			var responseWrapper struct {
				Success bool `json:"success"`
				Error   struct {
					Code    string      `json:"code"`
					Message string      `json:"message"`
					Details interface{} `json:"details"`
				} `json:"error"`
			}

			// Parse response body into the wrapper
			err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
			require.NoError(t, err)

			// Verify error response
			assert.False(t, responseWrapper.Success)
			assert.Equal(t, "validation_error", responseWrapper.Error.Code)

			// Verify mock expectations
			mockService.AssertExpectations(t)
		})

	*/
}

// TestGetActiveSessions tests the GetActiveSessions handler
func TestGetActiveSessions(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Success", func(t *testing.T) {
		// Use a fixed time for testing instead of utils.TestTime()
		baseTime := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)

		// Expected sessions
		expectedSessions := []*models.ActiveSessionInfo{
			{
				ID:        "session-1",
				CreatedAt: baseTime,
				ExpiresAt: baseTime.Add(24 * time.Hour),
			},
			{
				ID:        "session-2",
				CreatedAt: baseTime.Add(-1 * time.Hour),
				ExpiresAt: baseTime.Add(23 * time.Hour),
			},
		}

		// Setup mock service
		mockService.On("GetUserActiveSessions", mock.Anything, int64(1001)).Return(expectedSessions, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/users/me/sessions", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetActiveSessions(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                        `json:"success"`
			Data    []*models.ActiveSessionInfo `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, len(expectedSessions), len(responseWrapper.Data))
		assert.Equal(t, expectedSessions[0].ID, responseWrapper.Data[0].ID)
		assert.Equal(t, expectedSessions[1].ID, responseWrapper.Data[1].ID)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("GET", "/api/users/me/sessions", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetActiveSessions(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("GetUserActiveSessions", mock.Anything, int64(1001)).Return(nil, errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/users/me/sessions", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetActiveSessions(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Empty Sessions", func(t *testing.T) {
		// Empty sessions list
		var emptySessions []*models.ActiveSessionInfo

		// Setup mock service
		mockService.On("GetUserActiveSessions", mock.Anything, int64(1001)).Return(emptySessions, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/users/me/sessions", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetActiveSessions(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                        `json:"success"`
			Data    []*models.ActiveSessionInfo `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Empty(t, responseWrapper.Data)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// TestInvalidateSession tests the InvalidateSession handler
func TestInvalidateSession(t *testing.T) {
	// Setup
	handler, mockService := setupUserTest(t)

	t.Run("Success", func(t *testing.T) {
		// Create request payload
		req := struct {
			SessionID string `json:"session_id"`
		}{
			SessionID: "session-123",
		}

		// Setup mock service
		mockService.On("InvalidateSession", mock.Anything, int64(1001), "session-123").Return(nil).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me/sessions", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.InvalidateSession(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Data    struct {
				Message string `json:"message"`
			} `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content
		assert.True(t, responseWrapper.Success)
		assert.Equal(t, "Session successfully invalidated", responseWrapper.Data.Message)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"session_id": invalid}`)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me/sessions", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.InvalidateSession(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Missing Session ID", func(t *testing.T) {
		// Create request payload without session ID
		req := struct {
			SessionID string `json:"session_id"`
		}{
			SessionID: "",
		}

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me/sessions", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.InvalidateSession(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "validation_error", responseWrapper.Error.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		req := struct {
			SessionID string `json:"session_id"`
		}{
			SessionID: "session-123",
		}
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request without auth context
		httpReq, err := http.NewRequest("DELETE", "/api/users/me/sessions", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.InvalidateSession(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		req := struct {
			SessionID string `json:"session_id"`
		}{
			SessionID: "session-123",
		}

		// Setup mock service to return error
		mockService.On("InvalidateSession", mock.Anything, int64(1001), "session-123").Return(errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me/sessions", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.InvalidateSession(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Forbidden Error", func(t *testing.T) {
		// Create request payload
		req := struct {
			SessionID string `json:"session_id"`
		}{
			SessionID: "other-user-session",
		}

		// Setup mock service to return forbidden error
		mockService.On("InvalidateSession", mock.Anything, int64(1001), "other-user-session").
			Return(utils.NewForbiddenError("You do not have permission to invalidate this session")).Once()

		// Create request body
		requestBody, err := json.Marshal(req)
		require.NoError(t, err)

		// Create test request
		httpReq, err := http.NewRequest("DELETE", "/api/users/me/sessions", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq = httpReq.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.InvalidateSession(rr, httpReq)

		// Verify response
		assert.Equal(t, http.StatusForbidden, rr.Code)

		// Define wrapper for the error response envelope
		var responseWrapper struct {
			Success bool `json:"success"`
			Error   struct {
				Code    string      `json:"code"`
				Message string      `json:"message"`
				Details interface{} `json:"details"`
			} `json:"error"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify error response
		assert.False(t, responseWrapper.Success)
		assert.Equal(t, "forbidden", responseWrapper.Error.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}
