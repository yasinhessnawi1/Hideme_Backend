package constants

// Base Routes
const (
	APIBasePath = "/api"
	HealthPath  = "/health"
	VersionPath = "/version"
	RoutesPath  = "/api/routes"
)

// Authentication Routes
const (
	AuthBasePath        = "/api/auth"
	AuthRegisterPath    = "/api/auth/signup"
	AuthLoginPath       = "/api/auth/login"
	AuthRefreshPath     = "/api/auth/refresh"
	AuthLogoutPath      = "/api/auth/logout"
	AuthLogoutAllPath   = "/api/auth/logout-all"
	AuthVerifyPath      = "/api/auth/verify"
	AuthValidateKeyPath = "/api/auth/validate-key"
)

// User Routes
const (
	UsersBasePath          = "/api/users"
	UserCheckUsernamePath  = "/api/users/check/username"
	UserCheckEmailPath     = "/api/users/check/email"
	UserProfilePath        = "/api/users/me"
	UserChangePasswordPath = "/api/users/me/change-password"
	UserSessionsPath       = "/api/users/me/sessions"
)

// API Key Routes
const (
	KeysBasePath  = "/api/keys"
	KeyDetailPath = "/api/keys/{keyID}"
)

// Settings Routes
const (
	SettingsBasePath   = "/api/settings"
	SettingsExportPath = "/api/settings/export"
	SettingsImportPath = "/api/settings/import"

	// Ban List Routes
	BanListBasePath  = "/api/settings/ban-list"
	BanListWordsPath = "/api/settings/ban-list/words"

	// Pattern Routes
	PatternsBasePath  = "/api/settings/patterns"
	PatternDetailPath = "/api/settings/patterns/{patternID}"

	// Entity Routes
	EntitiesBasePath         = "/api/settings/entities"
	EntityByMethodPath       = "/api/settings/entities/{methodID}"
	EntityDetailPath         = "/api/settings/entities/{entityID}"
	EntityDeleteByMethodPath = "/api/settings/entities/delete_entities_by_method_id/{methodID}"
)

// Database Generic Routes
const (
	DBBasePath        = "/api/db"
	DBTablePath       = "/api/db/{table}"
	DBTableRecordPath = "/api/db/{table}/{id}"
	DBTableSchemaPath = "/api/db/{table}/schema"
)

// URL Parameters
const (
	ParamKeyID     = "keyID"
	ParamEntityID  = "entityID"
	ParamMethodID  = "methodID"
	ParamPatternID = "patternID"
	ParamTable     = "table"
	ParamID        = "id"
)

// Query Parameters
const (
	QueryParamPage     = "page"
	QueryParamPageSize = "page_size"
	QueryParamUsername = "username"
	QueryParamEmail    = "email"
)
