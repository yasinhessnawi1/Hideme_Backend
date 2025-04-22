package models

import "time"

// SettingsExport represents the complete set of user settings for export/import
type SettingsExport struct {
	UserID          int64                    `json:"user_id"`
	ExportDate      time.Time                `json:"export_date"`
	GeneralSettings *UserSetting             `json:"general_settings"`
	BanList         *BanListWithWords        `json:"ban_list"`
	SearchPatterns  []*SearchPattern         `json:"search_patterns"`
	ModelEntities   []*ModelEntityWithMethod `json:"model_entities"`
}
