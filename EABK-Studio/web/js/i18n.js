const labels={ja:{dashboard:"ダッシュボード",tables:"表",source:"ソース",search:"検索",repo:"リポジトリ",updated:"更新を検知しました。モデルを再読込しました。",noData:"管理データがありません"},en:{dashboard:"Dashboard",tables:"Tables",source:"Source",search:"Search",repo:"Repository",updated:"Update detected; model reloaded.",noData:"No management data"}};
export function t(key){return labels[window.__lang||"ja"][key]||key;}
export function toggleLanguage(){window.__lang=window.__lang==="en"?"ja":"en";document.documentElement.lang=window.__lang;window.dispatchEvent(new Event("languagechange"));}
