# pyside6-lupdate 用プロジェクトファイル
#
# 使い方:
#   cd hve/gui/i18n
#   pyside6-lupdate translations.pro
#   # → hve_gui_en_US.ts が更新される
#   pyside6-lrelease translations.pro
#   # → hve_gui_en_US.qm が生成される
#
# ソース言語は日本語（ja_JP）のため ja_JP の .ts/.qm は生成しない。

SOURCES = ../app.py \
          ../app_catalog_loader.py \
          ../copilot_chat_panel.py \
          ../copy_button.py \
          ../doc_convert.py \
          ../header_bar.py \
          ../help_content.py \
          ../help_popup.py \
          ../main_window.py \
          ../mdq_index_service.py \
          ../page_intro.py \
          ../page_options.py \
          ../page_options_ard.py \
          ../page_workbench.py \
          ../page_workflow_select.py \
          ../session_menu.py \
          ../settings_apply.py \
          ../settings_window.py \
          ../stats_detail_popup.py \
          ../tasktre_widget.py \
          ../wizard.py \
          ../workbench_logger.py \
          ../workbench_state.py \
          ../workbench_widgets.py \
          ../workbench_window.py \
          ../widgets/app_id_checklist.py

TRANSLATIONS = hve_gui_en_US.ts

CODECFORTR = UTF-8
CODECFORSRC = UTF-8
