"""
ZephIR: multiple object tracking via image registration

See /docs/Guide-parameters.md for detailed explanations and tips for using optional arguments.

Usage:
    zephir -h | --help
    zephir -v | --version
    zephir --dataset=<dataset> [options]

Options:
    -h --help                           show this message and exit.
    -v --version                        show version information and exit.
    --dataset=<dataset>                 path to data directory to analyze.
    --filename=<filename>               name of the video file.
    --args=<arg_dict>                   dict containing args
    --load_checkpoint=<load_checkpoint> resume from last checkpoint. [default: False]
    --load_args=<load_args>             load arguments from existing args.json file. [default: False]
    --allow_rotation=<allow_rotation>   enable rho parameter to rotate descriptors. [default: False]
    --channel=<channel>                 data channel to register.
    --clip_grad=<clip_grad>             maximum value for gradients; use -1 to uncap gradients. [default: 1.0]
    --cuda=<cuda>                       check if a CUDA-compatible GPU is available for  use. [default: True]
    --dimmer_ratio=<dimmer_ratio>       ratio to dim out non-foveated regions. [default: 0.1]
    --exclude_self=<excluse_self>       exclude annotations with provenance 'NEIR'. [default: True]
    --exclusive_prov=<exclusive_prov>   only load annotations with given provenance.
    --fovea_sigma=<fovea_sigma>         sigma for gaussian mask for foveated regions; use -1 to disable. [default: 2.5]
    --gamma=<gamma>                     gamma correction coefficient. [default: 2]
    --grid_shape=<grid_shape>           size of image descriptor in the xy-plane. [default: 25]
    --include_all=<include_all>         include all existing annotations in save file. [default: True]
    --lambda_d=<lambda_d>               coefficient for center detection loss. [default: -1.0]
    --lambda_n=<lambda_n>               coefficient for intra-keypoint spring constant. [default: 1.0]
    --lambda_n_mode=<lambda_n_mode>     method by which spring loss is calculated. [default: disp]
    --lambda_t=<lambda_t>               coefficient for temporal loss. [default: -1.0]
    --load_nn=<load_nn>                 load in manually defined spring connections if available. [default: True]
    --lr_ceiling=<lr_ceiling>           maximum value for initial learning rate. [default: 0.2]
    --lr_coef=<lr_coef>                 coefficient for initial learning rate. [default: 2.0]
    --lr_floor=<lr_floor>               minimum value for initial learning rate. [default: 0.02]
    --motion_predict=<motion_predict>   enable flow field motion prediction with partial annotations. [default: False]
    --n_chunks=<n_chunks>               number of steps to divide the forward pass into. [default: 10]
    --n_epoch=<n_epoch>                 number of iterations. [default: 40]
    --n_epoch_d=<n_epoch_d>             number of iterations for center detection. [default: 10]
    --n_frame=<n_frame>                 number of frames to analyze for temporal loss. [default: 1]
    --n_ref=<n_ref>                     override for shape_n; requires an annotated frames with exactly n_ref keypoints.
    --nn_max=<nn_max>                   maximum number of neighbors connected for spring loss. [default: 5]
    --save_mode=<save_mode>             mode for saving results. [default: o]
    --sort_mode=<sort_mode>             method for sorting frame order and parent-child tree. [default: similarity]
    --t_ignore=<t_ignore>               frames to ignore for analysis.
    --t_ref=<t_ref>                     override for reference frames to search for annotations.
    --t_track=<t_track>                 frames to include for analysis; supercedes t_ignore.
    --wlid_ref=<wlid_ref>               subset of keypoints to track by worldline_id; supercedes n_ref.
    --z_compensator=<z_compensator>     number of additional gradient descent steps for z-axis. [default: -1.0]
"""

import shutil
from docopt import docopt
import sys

from zephir.__version__ import __version__
from zephir.methods import *
from zephir.models.container import Container
from zephir.utils.io import *
from source.clibs import n_io
from source.clibs.zephir.methods import save_movie, track_all, build_tree


def run_zephir(dataset: Path, args: dict, filename=None):

    if not (dataset / 'backup').is_dir():
        Path.mkdir(dataset / 'backup')

    if args['--load_checkpoint'] in ['True', 'Y', 'y']:
        args = n_io.get_checkpoint(dataset, 'args', verbose=True, filename=filename)
        state = n_io.get_checkpoint(dataset, 'state', filename=filename)
        if args is None or state is None:
            print('*** CHECKPOINT EMPTY! Exiting...')
            exit()
    else:
        if (
            args['--load_args'] in ['True', 'Y', 'y'] and
            (dataset / 'args.json').is_file()
        ):
            with open(str(dataset / 'args.json')) as json_file:
                args = json.load(json_file)

        n_io.update_checkpoint(
            dataset,
            {'state': 'init',
             '__version__': __version__,
             'args': args},
            filename = filename
        )
        state = 'init'

    # checking for available CUDA GPU
    if args['--cuda'] in ['True', 'Y', 'y'] and torch.cuda.is_available():
        print('\n*** GPU available!')
        dev = 'cuda'
    # elif torch.backends.mps.is_available():
    #     dev = 'mps'
    else:
        dev = 'cpu'
    print(f'\nUsing device: {dev}\n\n')

    # building/loading variable container
    if state == 'init':

        print("Initializing...")
        container = Container(
            dataset=dataset,
            allow_rotation=args['--allow_rotation'] in ['True', 'Y', 'y'],
            channel=int(args['--channel']) if args['--channel'] else None,
            dev=dev,
            exclude_self=args['--exclude_self'] in ['True', 'Y', 'y'],
            exclusive_prov=(bytes(args['--exclusive_prov'], 'utf-8')
                            if args['--exclusive_prov'] else None),
            gamma=float(args['--gamma']),
            include_all=args['--include_all'] in ['True', 'Y', 'y'],
            lr_coef=float(args['--lr_coef']),
            n_frame=int(args['--n_frame']),
            z_compensator=float(args['--z_compensator']),
        )

        n_io.update_checkpoint(dataset, {'state': 'load'}, filename=filename)
        state = 'load'

    else:
        container = n_io.get_checkpoint(dataset, 'container', filename=filename)

    # building annotations table and tracking models
    if state == 'load':

        print("Loading...")
        container, results = build_annotations(
            container=container,
            annotation=None,
            t_ref=eval(args['--t_ref']) if args['--t_ref'] else None,
            wlid_ref=eval(args['--wlid_ref']) if args['--wlid_ref'] else None,
            n_ref=int(args['--n_ref']) if args['--n_ref'] else None,
        )

        n_io.update_checkpoint(dataset, {'state': 'build'}, filename=filename)
        state = 'build'

    else:
        results = n_io.get_checkpoint(dataset, 'results', filename=filename)

    # compiling spring network and frame tree
    if state == 'build':

        print("Building...")
        print("Building models!")
        container, zephir, zephod = build_models(
            container=container,
            dimmer_ratio=float(args['--dimmer_ratio']),
            grid_shape=(5, 2 * (int(args['--grid_shape']) // 2) + 1,
                        2 * (int(args['--grid_shape']) // 2) + 1),
            fovea_sigma=(1, float(args['--fovea_sigma']),
                         float(args['--fovea_sigma'])),
            n_chunks=int(args['--n_chunks']),
        )

        print("Building springs!")
        container = build_springs(
            container=container,
            load_nn=args['--load_nn'] in ['True', 'Y', 'y'],
            nn_max=int(args['--nn_max']),
        )

        print("Building trees!")
        container = build_tree.build_tree(
            container=container,
            sort_mode=str(args['--sort_mode']),
            t_ignore=eval(args['--t_ignore']) if args['--t_ignore'] else None,
            t_track=eval(args['--t_track']) if args['--t_track'] else None,
            filename=filename
        )

        n_io.update_checkpoint(dataset, {'state': 'track', '_t_list': None}, filename=filename)
        state = 'track'

    else:
        zephir = get_checkpoint(dataset, 'zephir', filename=filename)
        zephod = get_checkpoint(dataset, 'zephod', filename=filename)

    # tracking all frames in _t_list
    if state == 'track':

        print("Tracking all!")
        container, results = track_all.track_all(
            container=container,
            results=results,
            zephir=zephir,
            zephod=zephod,
            clip_grad=float(args['--clip_grad']),
            lambda_t=float(args['--lambda_t']),
            lambda_d=float(args['--lambda_d']),
            lambda_n=float(args['--lambda_n']),
            lambda_n_mode=args['--lambda_n_mode'],
            lr_ceiling=float(args['--lr_ceiling']),
            lr_floor=float(args['--lr_floor']),
            motion_predict=args['--motion_predict'] in ['True', 'Y', 'y'],
            n_epoch=int(args['--n_epoch']),
            n_epoch_d=(int(args['--n_epoch_d'])
                       if float(args['--lambda_d']) > 0 else 0),
            _t_list=get_checkpoint(dataset, '_t_list'),
            filename=filename
        )

    else:
        results = n_io.get_checkpoint(dataset, 'results', verbose=True, filename=filename)

    if np.any(np.isnan(results)):
        print(f'*** WARNING: NaN found in: '
              f'{list(np.unique(np.where(np.isnan(results))[0]))}')
        results = np.where(np.isfinite(results), results, 0)
        n_io.update_checkpoint(dataset, {'results': results}, filename=filename)

    save_annotations(
        container=container,
        results=results,
        save_mode=str(args['--save_mode']),
    )

    save_movie(
        container=container,
        results=results,
        filename=filename
    )

    now = datetime.datetime.now()
    now_ = now.strftime("%m_%d_%Y_%H_%M_%S")
    shutil.copy(dataset / 'checkpoint.pt',
                dataset / 'backup' / f'checkpoint_{now_}.pt')

    print('\n\n*** DONE!')
    return_code = 0
    return


def main():
    args = docopt(__doc__, version=f'ZephIR {__version__}')
    # print(args, '\n')

    dataset = Path(args['--dataset']).parent
    filename = Path(args['--dataset']).name

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        print('Running deployed...')
        # freeze_support()
        # print("Starting multiprocessing manager...")
        # manager = Manager()
        # print("Multiprocessing manager working.")
    else:
        print('Running in a normal Python process...')

    run_zephir(
        dataset=Path(dataset),
        args=args,
        filename=Path(filename),
    )


if __name__ == '__main__':
    main()
