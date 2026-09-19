% ENGR 315L Control Systems Lab
% Author: [Student Name]
% Date: [MM/DD/YYYY]    version 2
% Title: Model curve with reference lines overlaid
% File Name: [StudentName]_Lab[N]_v2.m
%
% ILLUSTRATIVE ONLY. Invented system and values; not a lab problem or answer.
% Shows: adding curves to an existing axes with hold on / hold off, keeping
% plot handles so the legend names exactly the traces meant, and giving the
% overlay a line style of its own so it stays distinct in grayscale.

clc; close all; clear all;

% Code starts here:
Vs  = 12;                  % step input amplitude [V]
tau = 1.1;                 % time constant [s]
t   = 0:0.005:8;           % time vector [s]

v = Vs * (1 - exp(-t/tau));
hm = plot(t, v, '-k', 'LineWidth', 1.5);   % the model

hold on;                                   % keep the model, add to the axes
v63 = (1 - exp(-1)) * Vs;                  % 63.2 % of the final value
hr  = plot([0 t(end)], [v63 v63], ':k', ...          % reference level
           [tau tau],  [0 v63],  ':k');              % drop line at t = tau
hf  = plot([0 t(end)], [Vs Vs], '--', 'Color', [0.5 0.5 0.5]);  % final value
hold off;

xlim([0 6]);
ylim([0 1.1*Vs]);
title('Step response with 63.2 % reference');
xlabel('Time [sec]');
ylabel('v_C(t) [V]');
% Name only the handles that carry meaning; the drop line shares hr(1)'s style.
legend([hm hr(1) hf], ...
       {'model, \tau = 1.1 s', '63.2 % of final value', 'final value V_s'}, ...
       'Location', 'southeast');
