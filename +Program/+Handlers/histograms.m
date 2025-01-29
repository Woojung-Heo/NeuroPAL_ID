classdef histograms
    
    properties (Constant)
        handles = dictionary( ...
            'panels', {"%s_hist_panel"}, ...
            'labels', {"%s_Label"}, ...
            'axes', {"%s_hist_ax"});

        prefixes = {'tl', 'tm', 'tr', 'bl', 'bm', 'br'};
    end
    
    methods (Static)
        function reset(pfx)
            if nargin == 0
                prefixes = Program.Handlers.histograms.prefixes;

                for n=1:length(prefixes)
                    Program.Handlers.histograms.reset(prefixes{n});
                end

                return
            end

            component = Program.Routines.GUI.get_component('panels', pfx);
            component.Visible = 'off';
            cla(Program.Routines.GUI.get_component('axes', pfx))
        end
        
        function draw()
            app = Program.app;
            raw = Program.GUIHandling.get_active_volume(app, 'request', 'array');

            Program.Handlers.histograms.reset();
            for c=1:length(app.proc_channel_grid.RowHeight)
                checkbox = Program.Routines.GUI.get_component('pp_cb', c);
                if checkbox.Value
                    dropdown = Program.Routines.GUI.get_component('pp_dd', c);
                    reference = Program.Helpers.get_reference(c);

                    chan_hist = raw.array(:, :, :, find(ismember(dropdown.Items, dropdown.Value)));

                    if app.HidezerointensitypixelsCheckBox.Value
                        chan_hist = chan_hist(chan_hist>0);
                    end
                    
                    if max(chan_hist, [], 'all') <= 1
                        chan_hist = chan_hist * app.ProcNoiseThresholdKnob.Limits(2);
                    end

                    [h_panel, h_label, h_axes] = Program.Handlers.histograms.get_gui(c);
                    h_panel.Visible = 'on';

                    h_label.Text = sprintf("%s Channel", reference.name);
                    histogram(h_axes, chan_hist, ...
                        'FaceColor', reference.color, ...
                        'EdgeColor', reference.color)
                    h_axes.XLim = [app.HidezerointensitypixelsCheckBox.Value, h_axes.XLim(2)];

                    if c >= 4
                        h_panel.Parent = app.ProcHistogramGrid;
                        h_panel.Layout.Row = 2;
                        h_panel.Layout.Column = c-3;
                    end
                end
            end
            
        end
    end

    methods(Static, Access=private)
        function [h_panel, h_label, h_axes] = get_gui(c)
            h_panel = Program.Routines.GUI.get_component('panels', Program.Handlers.histograms.prefixes{c});
            h_label = Program.Routines.GUI.get_component('labels', Program.Handlers.histograms.prefixes{c});
            h_axes = Program.Routines.GUI.get_component('axes', Program.Handlers.histograms.prefixes{c});
        end
    end
end

