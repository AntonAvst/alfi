import yaml
import os


class ConfigManager():
    def __init__(self):
        self.configs_dir = '.\configs'
        self.configs = {}
        self.load_configs()

    def load_configs(self):
        for file_name in os.listdir(self.configs_dir):
            if file_name.endswith(('.yaml', 'yml')):
                self.configs[file_name] = self.load_yaml(self.configs_dir + '\\' + file_name)
        
    def load_yaml(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
        
    def update_config(self, key, value, config_name='place_holder.yaml'):
        file_path = self.configs_dir + config_name
        # load existing config
        with open(file_path, 'r', encoding='utf-8') as file:
            config_data = yaml.safe_load(file)
        
        config_data[key] = value

        with open(file_path, 'w', encoding='utf-8') as file:
            yaml.dump(config_data, file, default_flow_style=False, allow_unicode=True)
    

config_manager = ConfigManager()