import json
import shutil
import os
import pickle
from callback import MultiClassAUROC, MultiGPUModelCheckpoint
from configparser import ConfigParser
from generator import AugmentedImageSequence
from keras.callbacks import ModelCheckpoint, TensorBoard, ReduceLROnPlateau
from keras.optimizers import Adam
from keras.utils import multi_gpu_model
from models.model import ModelFactory
import utility

def main():

    # Instantiate config parser
    # as long as a configuration file is in the local directory of this training code
    # it will be utilized by the training script

    # TODO : Add a README for the configuration file used to configure this training cycle
    config_file = "./sample_config.ini"
    cp = ConfigParser()
    cp.read(config_file)

    # set a bunch of default config
    output_directory = cp["DEFAULT"].get("output_directory")
    image_source_directory = cp["DEFAULT"].get("image_source_directory")
    base_model_name = cp["DEFAULT"].get("base_model_name")
    # Class names are passed in as array within the configuration script
    class_names = cp["DEFAULT"].get("class_names").split(",")

    # training configuration
    # See sample_config.ini for explanation of all of the parameters
    use_base_model_weights = cp["TRAIN"].getboolean("use_base_model_weights")
    use_trained_model_weights = cp["TRAIN"].getboolean("use_trained_model_weights")
    use_best_weights = cp["TRAIN"].getboolean("use_best_weights")
    output_weights_name = cp["TRAIN"].get("output_weights_name")
    epochs = cp["TRAIN"].getint("epochs")
    batch_size = cp["TRAIN"].getint("batch_size")
    initial_learning_rate = cp["TRAIN"].getfloat("initial_learning_rate")
    generator_workers = cp["TRAIN"].getint("generator_workers")
    image_dimension = cp["TRAIN"].getint("image_dimension")
    train_steps = cp["TRAIN"].get("train_steps")
    patience_reduce_lr = cp["TRAIN"].getint("reduce_learning_rate")
    min_learning_rate = cp["TRAIN"].getfloat("min_learning_rate")
    validation_steps = cp["TRAIN"].get("validation_steps")
    positive_weights_multiply = cp["TRAIN"].getfloat("positive_weights_multiply")
    dataset_csv_dir = cp["TRAIN"].get("dataset_csv_dir")

    if use_trained_model_weights:
        print("<<< Using pretrained model weights! >>>")
        training_stats_file = os.path.join(output_directory, ".training_stats.json")
        if os.path.isfile(training_stats_file):
            training_stats = json.load(open(training_stats_file))
        else: 
            training_stats = {}
    
    show_model_summary = cp["TRAIN"].getboolean("show_model_summary")
    # end configuration parser

    utility.check_create_output_dir(output_directory)

    utility.backup_config_file(output_directory, config_file)

    train_counts, train_pos_counts = utility.get_sample_counts(output_directory, "train", class_names)
    validation_counts, _ = utility.get_sample_counts(output_directory, "validation", class_names)

    # compute steps

    # train steps var defined in config ini file
    # if set to standard auto, normalize train_steps
    # wrt batch_size, otherwise take user input
    if train_steps == "auto":
        train_steps = int(train_counts / batch_size)
    else:
        try:
            train_steps = int(train_steps)
        except:
            ValueError:
                raise ValueError(f"""
                train_steps : {train_steps} is invalid,
                please use 'auto' or specify an integer.
                """)
        print(f" <<< train_steps : {train_steps} >>>")

        if validation_steps == "auto":
            validation_steps = int(validation_counts / batch_size)
        else:
            try:
                validation_steps = int(validation_steps)
            except:
                ValueError:
                    raise ValueError(f"""
                    validation_steps : {validation_steps} is invalid,
                    please use 'auto' or specify an integer.
                    """)
        print(f" <<< validation_steps : {validation_steps} >>>")

        # class weights
        class_weights = utility.get_class_weights(
            train_counts,
            train_pos_counts,
            multiply=positive_weights_multiply,
        )
        print(f"class_weights : {class_weights}")

        print(" <<< Loading Model >>>")
        if use_trained_model_weights:
            if use_best_weights:
                model_weights_file = os.path.join(output_directory, f"best_{output_weights_name}")
            else:
                model_weights_file = os.path.join(output_directory, output_weights_name)
        else:
            model_weights_file = None
        
        model_factory = ModelFactory()
        model = model_factory.get_model(
            class_names=class_names,
            use_base_weights=use_base_model_weights,
            weights_path=model_weights_file,
            intput_shape=(image_dimension,image_dimension,3)
        )

        if show_model_summary:
            print(model.summary())
        
        print(" <<< Creating Image Generators >>> ")
        train_sequence = AugmentedImageSequence(
            dataset_csv_dir=os.path.join(output_directory, "train.csv"),
            class_names=class_names,
            source_image_dir=image_source_directory,
            batch_size=batch_size,
            target_size=(image_dimension, image_dimension),
            augmenter=augmenter,
            steps=train_steps,
        )
        
        validation_sequence = AugmentedImageSequence(
            dataset_csv_dir=os.path.join(output_directory, "validation.csv"),
            class_names=class_names,
            source_image_dir=image_source_directory,
            batch_size=batch_size,
            target_size=(image_dimension, image_dimension)
        )
            
            