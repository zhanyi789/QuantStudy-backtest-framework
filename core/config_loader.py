import yaml


def load_config(yaml_path):
    """
    載入 YAML 設定檔並展平結構，使得 engine 和其他模組可直接讀取。

    P2-1: 將 YAML 的 system:、engine: 子區段提升至頂層
          讀取 enabled: true 的策略/sizer 參數並提升
          返回一個 flat dict，可直接傳給 AdvancedEventEngine

    參數：
        yaml_path (str): YAML 設定檔路徑

    返回：
        dict: 展平後的設定字典
    """
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 建立最終的 flat dict
    flat_config = {}

    # 1. 提升 system: 區段
    if 'system' in config:
        flat_config.update(config['system'])

    # 2. 提升 engine: 區段（優先級高於 system）
    if 'engine' in config:
        flat_config.update(config['engine'])

    # 3. 讀取 enabled: true 的策略參數
    if 'strategies' in config:
        for strategy_name, strategy_cfg in config['strategies'].items():
            if strategy_cfg.get('enabled', False):
                # 將策略參數提升，但保留策略名稱作為前綴，避免衝突
                flat_config['strategy_name'] = strategy_name
                for key, value in strategy_cfg.items():
                    if key != 'enabled':
                        flat_config[key] = value
                break  # 只讀第一個啟用的策略

    # 4. 讀取 enabled: true 的 sizer 參數
    if 'sizers' in config:
        for sizer_name, sizer_cfg in config['sizers'].items():
            if sizer_cfg.get('enabled', False):
                flat_config['sizer_name'] = sizer_name
                for key, value in sizer_cfg.items():
                    if key != 'enabled':
                        flat_config[key] = value
                break  # 只讀第一個啟用的 sizer

    # 5. 讀取全局濾網與消融濾網
    if 'global_filters' in config:
        flat_config.update(config['global_filters'])

    if 'ablation_filters' in config:
        flat_config.update(config['ablation_filters'])

    # 6. 讀取 enabled: true 的出場模組清單（保留為列表，engine 單獨處理）
    if 'exits' in config:
        enabled_exits = [
            {k: v for k, v in exit_cfg.items() if k != 'enabled'}
            for exit_cfg in config['exits']
            if exit_cfg.get('enabled', False)
        ]
        flat_config['exits_config'] = enabled_exits

    return flat_config


if __name__ == '__main__':
    # 簡單測試
    cfg = load_config('config.yaml')
    print("✅ Config loaded successfully!")
    print(f"策略: {cfg.get('strategy_name')}")
    print(f"資金管理: {cfg.get('sizer_name')}")
    print(f"最大持倉: {cfg.get('max_positions')}")
