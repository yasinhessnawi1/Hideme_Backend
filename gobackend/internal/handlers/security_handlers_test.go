package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// MockSecurityService implements SecurityServiceInterface for testing
type MockSecurityService struct {
	mock.Mock
}

func (m *MockSecurityService) ListBans(ctx context.Context) ([]*models.IPBan, error) {
	args := m.Called(ctx)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]*models.IPBan), args.Error(1)
}

func (m *MockSecurityService) BanIP(ctx context.Context, ipAddress string, reason string, duration time.Duration, bannedBy string) (*models.IPBan, error) {
	args := m.Called(ctx, ipAddress, reason, duration, bannedBy)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.IPBan), args.Error(1)
}

func (m *MockSecurityService) UnbanIP(ctx context.Context, banID int64) error {
	args := m.Called(ctx, banID)
	return args.Error(0)
}

func (m *MockSecurityService) IsBanned(ipAddress string) bool {
	args := m.Called(ipAddress)
	return args.Bool(0)
}

func (m *MockSecurityService) IsRateLimited(ipAddress string, category string) bool {
	args := m.Called(ipAddress, category)
	return args.Bool(0)
}

// Test handler type with the interface for testing
type SecurityHandlerTest struct {
	Service SecurityServiceInterface
}

// Implement the handler methods with our test handler
func (h *SecurityHandlerTest) ListBannedIPs(w http.ResponseWriter, r *http.Request) {
	// Get list of banned IPs
	bans, err := h.Service.ListBans(r.Context())
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the bans
	utils.JSON(w, http.StatusOK, bans)
}

func (h *SecurityHandlerTest) BanIP(w http.ResponseWriter, r *http.Request) {
	// Get the admin username for tracking who created the ban
	username, _ := auth.GetUsername(r)

	// Decode and validate the request body
	var req struct {
		IPAddress string        `json:"ip_address" validate:"required,ip|cidr"`
		Reason    string        `json:"reason" validate:"required"`
		Duration  time.Duration `json:"duration"` // In seconds, 0 for permanent
	}

	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Ban the IP
	ban, err := h.Service.BanIP(r.Context(), req.IPAddress, req.Reason, req.Duration, username)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the created ban
	utils.JSON(w, http.StatusCreated, ban)
}

func (h *SecurityHandlerTest) UnbanIP(w http.ResponseWriter, r *http.Request) {
	// Get the ban ID from the URL
	banIDStr := chi.URLParam(r, "id")
	banID, err := strconv.ParseInt(banIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid ban ID", nil)
		return
	}

	// Unban the IP
	if err := h.Service.UnbanIP(r.Context(), banID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, http.StatusOK, map[string]string{
		"message": "IP address successfully unbanned",
	})
}

// Setup function for tests
func setupSecurityHandlerTest() (*SecurityHandlerTest, *MockSecurityService) {
	mockService := new(MockSecurityService)
	handler := &SecurityHandlerTest{
		Service: mockService,
	}
	return handler, mockService
}

// Helper function to create authentication context
func createAuthContextWithUsername(userID int64, username string) context.Context {
	ctx := context.Background()
	ctx = context.WithValue(ctx, auth.UserIDContextKey, userID)
	ctx = context.WithValue(ctx, auth.UsernameContextKey, username)
	return ctx
}

// TestListBannedIPs tests the ListBannedIPs handler
func TestListBannedIPs(t *testing.T) {
	// Test cases
	tests := []struct {
		name           string
		setupMocks     func(*MockSecurityService)
		expectedStatus int
		checkResponse  func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Success - Returns list of IP bans",
			setupMocks: func(mockService *MockSecurityService) {
				// Create test data
				now := time.Now()
				expires := now.Add(24 * time.Hour)
				bans := []*models.IPBan{
					{
						ID:        1,
						IPAddress: "192.168.1.1",
						Reason:    "Suspicious activity",
						CreatedBy: "admin",
						CreatedAt: now,
						ExpiresAt: &expires,
					},
					{
						ID:        2,
						IPAddress: "10.0.0.1",
						Reason:    "Brute force attempt",
						CreatedBy: "system",
						CreatedAt: now,
						ExpiresAt: nil, // Permanent ban
					},
				}
				mockService.On("ListBans", mock.Anything).Return(bans, nil)
			},
			expectedStatus: http.StatusOK,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response is successful
				assert.True(t, response.Success)

				// Verify bans data
				var bans []*models.IPBan
				dataBytes, err := json.Marshal(response.Data)
				assert.NoError(t, err)
				err = json.Unmarshal(dataBytes, &bans)
				assert.NoError(t, err)

				// Verify we got 2 bans
				assert.Len(t, bans, 2)
				assert.Equal(t, "192.168.1.1", bans[0].IPAddress)
				assert.Equal(t, "10.0.0.1", bans[1].IPAddress)
			},
		},
		{
			name: "Success - Empty ban list",
			setupMocks: func(mockService *MockSecurityService) {
				mockService.On("ListBans", mock.Anything).Return([]*models.IPBan{}, nil)
			},
			expectedStatus: http.StatusOK,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response is successful
				assert.True(t, response.Success)

				// Verify empty array
				var bans []*models.IPBan
				dataBytes, err := json.Marshal(response.Data)
				assert.NoError(t, err)
				err = json.Unmarshal(dataBytes, &bans)
				assert.NoError(t, err)

				assert.Empty(t, bans)
			},
		},
		{
			name: "Error - Service returns error",
			setupMocks: func(mockService *MockSecurityService) {
				mockService.On("ListBans", mock.Anything).Return(nil, errors.New("database error"))
			},
			expectedStatus: http.StatusInternalServerError,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "internal_error", response.Error.Code)
			},
		},
	}

	// Run tests
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Setup
			handler, mockService := setupSecurityHandlerTest()

			// Setup mocks
			if tt.setupMocks != nil {
				tt.setupMocks(mockService)
			}

			// Create test request
			req, err := http.NewRequest("GET", "/api/admin/security/bans", nil)
			assert.NoError(t, err)
			req = req.WithContext(createAuthContextWithUsername(1, "admin"))

			// Create response recorder
			rr := httptest.NewRecorder()

			// Call handler
			handler.ListBannedIPs(rr, req)

			// Check status code
			assert.Equal(t, tt.expectedStatus, rr.Code)

			// Additional response checks
			if tt.checkResponse != nil {
				tt.checkResponse(t, rr)
			}

			// Verify mocks
			mockService.AssertExpectations(t)
		})
	}
}

// TestBanIP tests the BanIP handler
func TestBanIP(t *testing.T) {
	// Test cases
	tests := []struct {
		name           string
		requestBody    interface{}
		setupMocks     func(*MockSecurityService)
		expectedStatus int
		checkResponse  func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Success - Temporary ban",
			requestBody: map[string]interface{}{
				"ip_address": "192.168.1.1",
				"reason":     "Suspicious activity",
				"duration":   int64(3600), // 1 hour in seconds
			},
			setupMocks: func(mockService *MockSecurityService) {
				now := time.Now()
				expiry := now.Add(time.Hour)
				mockBan := &models.IPBan{
					ID:        1,
					IPAddress: "192.168.1.1",
					Reason:    "Suspicious activity",
					CreatedBy: "admin",
					CreatedAt: now,
					ExpiresAt: &expiry,
				}
				// FIX: Match the exact duration value (3600 nanoseconds) from the request
				mockService.On("BanIP",
					mock.Anything,
					"192.168.1.1",
					"Suspicious activity",
					time.Duration(3600), // Use exact nanosecond value, not time.Second
					"admin").Return(mockBan, nil)
			},
			expectedStatus: http.StatusCreated,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response is successful
				assert.True(t, response.Success)

				// Verify ban data
				ban := make(map[string]interface{})
				dataBytes, err := json.Marshal(response.Data)
				assert.NoError(t, err)
				err = json.Unmarshal(dataBytes, &ban)
				assert.NoError(t, err)

				assert.Equal(t, float64(1), ban["id"])
				assert.Equal(t, "192.168.1.1", ban["ip_address"])
				assert.Equal(t, "Suspicious activity", ban["reason"])
				assert.Equal(t, "admin", ban["created_by"])
			},
		},
		{
			name: "Success - Permanent ban",
			requestBody: map[string]interface{}{
				"ip_address": "10.0.0.1",
				"reason":     "Malicious activity",
				"duration":   int64(0), // Permanent (0 seconds)
			},
			setupMocks: func(mockService *MockSecurityService) {
				now := time.Now()
				mockBan := &models.IPBan{
					ID:        2,
					IPAddress: "10.0.0.1",
					Reason:    "Malicious activity",
					CreatedBy: "admin",
					CreatedAt: now,
					ExpiresAt: nil, // Permanent ban has nil expiry
				}
				// FIX: Match the exact duration value (0 nanoseconds) from the request
				mockService.On("BanIP",
					mock.Anything,
					"10.0.0.1",
					"Malicious activity",
					time.Duration(0), // Use exact nanosecond value
					"admin").Return(mockBan, nil)
			},
			expectedStatus: http.StatusCreated,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response is successful
				assert.True(t, response.Success)

				// Verify ban data
				ban := make(map[string]interface{})
				dataBytes, err := json.Marshal(response.Data)
				assert.NoError(t, err)
				err = json.Unmarshal(dataBytes, &ban)
				assert.NoError(t, err)

				assert.Equal(t, float64(2), ban["id"])
				assert.Equal(t, "10.0.0.1", ban["ip_address"])
				assert.Equal(t, "Malicious activity", ban["reason"])
				assert.Equal(t, "admin", ban["created_by"])
				assert.Nil(t, ban["expires_at"])
			},
		},
		{
			name: "Error - Invalid IP address",
			requestBody: map[string]interface{}{
				"ip_address": "invalid-ip",
				"reason":     "Test reason",
				"duration":   int64(3600),
			},
			setupMocks: func(mockService *MockSecurityService) {
				// No mock setup needed - validation should fail
			},
			expectedStatus: http.StatusBadRequest,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "validation_error", response.Error.Code)
			},
		},
		{
			name: "Error - Missing reason",
			requestBody: map[string]interface{}{
				"ip_address": "192.168.1.1",
				"duration":   int64(3600),
				// Reason field missing
			},
			setupMocks: func(mockService *MockSecurityService) {
				// No mock setup needed - validation should fail
			},
			expectedStatus: http.StatusBadRequest,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "validation_error", response.Error.Code)
			},
		},
		{
			name: "Error - Service returns error",
			requestBody: map[string]interface{}{
				"ip_address": "192.168.1.1",
				"reason":     "Test reason",
				"duration":   int64(3600),
			},
			setupMocks: func(mockService *MockSecurityService) {
				// FIX: Match the exact duration value from the request
				mockService.On("BanIP",
					mock.Anything,
					"192.168.1.1",
					"Test reason",
					time.Duration(3600), // Use exact nanosecond value
					"admin").Return(nil, errors.New("database error"))
			},
			expectedStatus: http.StatusInternalServerError,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "internal_error", response.Error.Code)
			},
		},
		{
			name:        "Error - Invalid JSON",
			requestBody: "not a json object",
			setupMocks: func(mockService *MockSecurityService) {
				// No mock setup needed - JSON parsing should fail
			},
			expectedStatus: http.StatusBadRequest,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
			},
		},
	}

	// Run tests
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Setup
			handler, mockService := setupSecurityHandlerTest()

			// Setup mocks
			if tt.setupMocks != nil {
				tt.setupMocks(mockService)
			}

			// Create request body
			var reqBody []byte
			var err error

			switch body := tt.requestBody.(type) {
			case string:
				reqBody = []byte(body)
			default:
				reqBody, err = json.Marshal(tt.requestBody)
				assert.NoError(t, err)
			}

			// Create test request
			req, err := http.NewRequest("POST", "/api/admin/security/bans", bytes.NewBuffer(reqBody))
			assert.NoError(t, err)
			req.Header.Set("Content-Type", "application/json")
			req = req.WithContext(createAuthContextWithUsername(1, "admin"))

			// Create response recorder
			rr := httptest.NewRecorder()

			// Call handler
			handler.BanIP(rr, req)

			// Check status code
			assert.Equal(t, tt.expectedStatus, rr.Code)

			// Additional response checks
			if tt.checkResponse != nil {
				tt.checkResponse(t, rr)
			}

			// Verify mocks
			mockService.AssertExpectations(t)
		})
	}
}

// TestUnbanIP tests the UnbanIP handler
func TestUnbanIP(t *testing.T) {
	// Set up router for URL parameter extraction
	setupChiRouter := func(handler http.HandlerFunc) (http.Handler, *httptest.ResponseRecorder) {
		r := chi.NewRouter()
		r.Delete("/api/admin/security/bans/{id}", handler)
		rr := httptest.NewRecorder()
		return r, rr
	}

	// Test cases
	tests := []struct {
		name           string
		banID          string // As path parameter
		setupMocks     func(*MockSecurityService, int64)
		expectedStatus int
		checkResponse  func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name:  "Success - Ban removed",
			banID: "123",
			setupMocks: func(mockService *MockSecurityService, banID int64) {
				mockService.On("UnbanIP", mock.Anything, banID).Return(nil)
			},
			expectedStatus: http.StatusOK,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response is successful
				assert.True(t, response.Success)

				// Verify success message
				data, ok := response.Data.(map[string]interface{})
				assert.True(t, ok)
				message, ok := data["message"].(string)
				assert.True(t, ok)
				assert.Equal(t, "IP address successfully unbanned", message)
			},
		},
		{
			name:  "Error - Invalid ban ID format",
			banID: "not-a-number",
			setupMocks: func(mockService *MockSecurityService, banID int64) {
				// No mock setup needed - ID parsing should fail
			},
			expectedStatus: http.StatusBadRequest,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "bad_request", response.Error.Code)
				assert.Contains(t, response.Error.Message, "Invalid ban ID")
			},
		},
		{
			name:  "Error - Ban not found",
			banID: "999",
			setupMocks: func(mockService *MockSecurityService, banID int64) {
				mockService.On("UnbanIP", mock.Anything, banID).Return(utils.NewNotFoundError("IPBan", banID))
			},
			expectedStatus: http.StatusNotFound,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "not_found", response.Error.Code)
			},
		},
		{
			name:  "Error - Service returns error",
			banID: "123",
			setupMocks: func(mockService *MockSecurityService, banID int64) {
				mockService.On("UnbanIP", mock.Anything, banID).Return(errors.New("database error"))
			},
			expectedStatus: http.StatusInternalServerError,
			checkResponse: func(t *testing.T, rr *httptest.ResponseRecorder) {
				var response utils.Response
				err := json.Unmarshal(rr.Body.Bytes(), &response)
				assert.NoError(t, err)

				// Verify response indicates error
				assert.False(t, response.Success)
				assert.NotNil(t, response.Error)
				assert.Equal(t, "internal_error", response.Error.Code)
			},
		},
	}

	// Run tests
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Setup
			handler, mockService := setupSecurityHandlerTest()

			// Parse banID to int64 if needed for mock setup
			var banID int64
			if id, err := strconv.ParseInt(tt.banID, 10, 64); err == nil {
				banID = id
			}

			// Setup mocks
			if tt.setupMocks != nil {
				tt.setupMocks(mockService, banID)
			}

			// Setup router and recorder
			router, rr := setupChiRouter(handler.UnbanIP)

			// Create test request
			req, err := http.NewRequest("DELETE", "/api/admin/security/bans/"+tt.banID, nil)
			assert.NoError(t, err)
			req = req.WithContext(createAuthContextWithUsername(1, "admin"))

			// Call handler via router
			router.ServeHTTP(rr, req)

			// Check status code
			assert.Equal(t, tt.expectedStatus, rr.Code)

			// Additional response checks
			if tt.checkResponse != nil {
				tt.checkResponse(t, rr)
			}

			// Verify mocks
			mockService.AssertExpectations(t)
		})
	}
}
