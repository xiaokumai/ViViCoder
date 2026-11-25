from datasets import load_dataset

def load_samples_to_dict():
    data = list(load_dataset("laylarsssss/FusedMHPP", "mhpp_210", split="test"))
    data_dict = {}
    for item in data:
        try:
            first_line = [item['test'].splitlines()[0]]
            
        except IndexError:
            first_line = ['assert min_stations([20,5,5,20,40,10,10,10]) == -1']
            
        data_dict[item["id"]] = first_line
    
    return data_dict

map_mhpp_sample_io = load_samples_to_dict()