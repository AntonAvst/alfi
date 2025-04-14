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
        
    def add_value_to_subcategory(self, new_key, new_value, nesting_levels=['categories','sub'], yaml_name='local_config.yaml'):
        yaml_path = self.configs_dir + '\\' + yaml_name
        with open(yaml_path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)

        data_pointer = data
        for level in nesting_levels:
            data_pointer = data_pointer[level]
        
        data_pointer[new_value] = new_key

        # Save back to file
        with open(yaml_path, 'w', encoding='utf-8') as file:
            yaml.dump(data, file, allow_unicode=True)
        

config_manager = ConfigManager()