%% This script compares PG detections vs Manual Aplose annotations
%3 vectors are created :
% % % % % %-A time vector is created from the 1st measurement to the end of the last
% % % % % %measurement with a user-defined time bin
% % % % % %-An Aplose vector with the timestamps of each annotation of the Aplose campaign
% % % % % %-A PG vector with the timestamps of each detection, the latter is then
% % % % % %formatted so that when one or more detection are present within an
% % % % % %Aplose box, a PG box with the same timestamps is created.
%The formatted PG vector and Aplose vector are then compared to estimate the performances of the PG detector   

clear;clc

%If choice = 1, all the waves are analysed
%If choice = 2, the user define a range of study
%TODO : gérer erreurs input
choice = 2;

%Time vector resolution
% time_bin = str2double(inputdlg("time bin ? (s)"));
time_bin = 10; %Same size than Aplose annotations

%If skip_Ap = 1, only PG detections are analysed
skip_Ap = 0;


%Add path with matlab functions from PG website
addpath(genpath('U:\Documents\Pamguard\pgmatlab'));
addpath(genpath('L:\acoustock\Bioacoustique\DATASETS\APOCADO\Code_MATLAB'));


%wav folder
folder_data_wav= uigetdir('','Select folder contening wav files');
if folder_data_wav == 0
    clc; disp("Select folder contening wav files - Error");
    return
end

%data folder
folder_data = fileparts(folder_data_wav);

%Binary folder
folder_data_PG = uigetdir(folder_data,'Select folder contening PAMGuard binary results');
if folder_data_PG == 0
    clc; disp("Select folder contening PAMGuard binary results - Error");
    return
end

switch choice
    case 2
    input1 = datetime(string(inputdlg("Date & Time beginning (dd MM yyyy HH mm ss) :")), 'InputFormat', 'dd MM yyyy HH mm ss', 'Format', 'yyyy MM dd  - HH mm ss');
    input2 = datetime(string(inputdlg("Date & Time end (dd MM yyyy HH mm ss) :")), 'InputFormat', 'dd MM yyyy HH mm ss', 'Format', 'yyyy MM dd  - HH mm ss');
end

%Infos from wav files
WavFolderInfo.wavList = dir(fullfile(folder_data_wav, '*.wav'));
WavFolderInfo.wavNames = string(extractfield(WavFolderInfo.wavList, 'name')');
WavFolderInfo.splitDates = split(WavFolderInfo.wavNames, [".","_"," - "],2);

%%%%%%%%%%%% TO ADAPT ACCORDING TO FILENAME %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% WavFolderInfo.wavDates = WavFolderInfo.splitDates(:,2); %APOCACO
% WavFolderInfo.wavDates_formated = datetime(WavFolderInfo.wavDates, 'InputFormat', 'yyMMddHHmmss', 'Format', 'yyyy MM dd - HH mm ss'); %APOCADO
WavFolderInfo.wavDates = strcat(WavFolderInfo.splitDates(:,2),'-',WavFolderInfo.splitDates(:,3)); %CETIROISE
WavFolderInfo.wavDates_formated = datetime(WavFolderInfo.wavDates, 'InputFormat', 'yyyy-MM-dd-HH-mm-ss', 'Format', 'yyyy MM dd - HH mm ss');%CETIROISE
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


for i = 1:length(WavFolderInfo.wavList)
    WavFolderInfo.wavinfo(i) = audioinfo(strcat(folder_data_wav,"\",string(WavFolderInfo.wavNames(i,:))));
end

%File selection
idx_file{1} = max(find(WavFolderInfo.wavDates_formated < input1));
if isempty(idx_file{1})
    idx_file_beg = 1;
else
    [min_val(1,1) min_idx(1,1)]= min(abs(input1-WavFolderInfo.wavDates_formated(idx_file{1}:idx_file{1}+1)));
    if min_idx(1,1) == 1
        idx_file_beg = idx_file{1};
    elseif min_idx(1,1) == 2
        idx_file_beg = idx_file{1}+1;
    end
end

idx_file{2} = min(find(WavFolderInfo.wavDates_formated > input2));
if isempty(idx_file{2})
    idx_file_end = length(WavFolderInfo.wavDates_formated);
else
    [min_val(1,2) min_idx(1,2)]= min(abs(input1-WavFolderInfo.wavDates_formated(idx_file{2}-1:idx_file{2})));
    if min_idx(1,2) == 1
        idx_file_end = idx_file{2}-1;
    elseif min_idx(1,2) == 2
        idx_file_end = idx_file{2};
    end
end

n_file_tot = length(WavFolderInfo.wavList);

WavFolderInfo.wavList([1:idx_file_beg-1,idx_file_end+1:end])=[];
WavFolderInfo.wavNames([1:idx_file_beg-1,idx_file_end+1:end])=[];
WavFolderInfo.splitDates([1:idx_file_beg-1,idx_file_end+1:end])=[];
WavFolderInfo.wavDates([1:idx_file_beg-1,idx_file_end+1:end])=[];
WavFolderInfo.wavDates_formated([1:idx_file_beg-1,idx_file_end+1:end])=[];
WavFolderInfo.wavinfo([1:idx_file_beg-1,idx_file_end+1:end])=[];

Firstname = char(WavFolderInfo.wavNames(1));
WavFolderInfo.txt_filename = string(Firstname(1,1:end-4));

clc;disp(strcat("1st wav : ", WavFolderInfo.wavList(1).name))
disp(strcat("last wav : ", WavFolderInfo.wavList(end).name))
disp(strcat(num2str(length(WavFolderInfo.wavList)),"/", num2str(n_file_tot), " files"))


%Aplose result file
if skip_Ap == 0
    %Aplose annotation csv file
    [Ap_data_name, Ap_datapath] = uigetfile(strcat(fileparts(folder_data_wav),'/*.csv'),'Select Aplose annotations');
    if Ap_data_name == 0
        clc; disp("Select Aplose annotations - Error");
        return
    end
end

%% Time vector creation
tic

for i = 1:length(WavFolderInfo.wavList)
    nb_bin_int(i,1) = fix(WavFolderInfo.wavinfo(i).Duration/time_bin); %number of complete aplose time bins per wav file
    last_bins(i,1) = mod(WavFolderInfo.wavinfo(i).Duration,time_bin); %last time bin per wav file
    bins(:,i) = [ones(nb_bin_int(i),1)*time_bin; last_bins(i)];
end
duration_time = bins(:); %All the time bins of the campaign
bins(find(bins==0))=[]; %delete zeros

time_vector =  [WavFolderInfo.wavDates_formated(1); WavFolderInfo.wavDates_formated(1) + cumsum(seconds(duration_time))];

% Deletion of annotation not within the wanted datetimes
idx0 = find(time_vector >= input1 == 0);
if ~isempty(idx0)
    time_vector(idx0,:) = [];
    duration_time(idx0,:) = [];
end

idx00 = find(dateshift(time_vector,'start','second') <= input2 == 0);
if ~isempty(idx00)
    time_vector(idx00,:) = [];
    duration_time(idx00(1:end-1),:) = [];
    duration_time(end,:) = [];
    
end

index_exclude = find(duration_time~=time_bin); %for now, one have to exlude those indexes for Aplose does not include them in the annotation campaign


datenum_time = datenum(time_vector);


elapsed_time.time_vector_creation = toc;



%% Creation of Aplose annotation vector
if skip_Ap == 0
    Ap_Annotation = importAploseSelectionTable(strcat(Ap_datapath,Ap_data_name),WavFolderInfo, time_vector, index_exclude);
%     Ap_Annotation = importAploseSelectionTable(strcat(Ap_datapath,Ap_data_name),WavFolderInfo, time_vector);

    %Selection of the annotator
    msg_annotator='Select the annotator';
    if length(unique(Ap_Annotation.annotator))>1
        opts=[unique(Ap_Annotation.annotator );"all"];
        selection_annotator=menu(msg_annotator,opts);
        annotator_selected = opts(selection_annotator);
        tic
        if annotator_selected ~= "all"
            counter_annotator = find(Ap_Annotation.annotator ~= annotator_selected);
            Ap_Annotation(counter_annotator,:)=[]; %Deletion of the annotations not correponding to the selected annotator
        end
    else
        annotator_selected = unique(Ap_Annotation.annotator);
    end

    %Selection of the annotation type
    msg_annotation='Select the annotion type to analyse';
    opts=[unique(Ap_Annotation.annotation )];
    selection_type_data=menu(msg_annotation,opts);
    type_selected = opts(selection_type_data);
    counter_annotation = find(Ap_Annotation.annotation ~= type_selected);
    Ap_Annotation(counter_annotation,:)=[]; %Deletion of the annotations not correponding to the type of annotation selected by user

    Ap_Annotation = sortrows(Ap_Annotation, 5);

    %If several annotators, delete duplicate annotations
    if annotator_selected == "all"
        [Ap_unique idx_unique CC]=unique(Ap_Annotation.start_datetime);
        Ap_Annotation = Ap_Annotation(idx_unique,:);
    end

    %Deletion of annotation not within the wanted datetimes
    idx1 = find(Ap_Annotation.start_datetime > input1 == 0);
    if ~isempty(idx1)
        Ap_Annotation(idx1,:) = [];
    end

    idx2 = find(Ap_Annotation.end_datetime < input2== 0);
    if ~isempty(idx2)
        Ap_Annotation(idx2,:) = [];
    end


    datenum_begin_Ap = datenum(Ap_Annotation.start_datetime);
    datenum_end_Ap = datenum(Ap_Annotation.end_datetime);

    duration_Ap = Ap_Annotation.end_time - Ap_Annotation.start_time;

    datenum_Ap = [datenum_begin_Ap, datenum_end_Ap]; %in second

    elapsed_time.Ap_vector_creation = toc;
end
%% Creation of PG annotations vector
tic
[PG_Annotation, is_click] = importBinary(folder_data_wav, WavFolderInfo, folder_data_PG, index_exclude, time_vector);
if exist('PG_Annotation','var') == 0
    clc; disp("Select PG detections - Error");
    return
end

%Deletion of annotation not within the wanted datetimes
idx3 = find(PG_Annotation.datetime_begin > input1 == 0);
if ~isempty(idx3)
    PG_Annotation(idx3,:) = [];
end

idx4 = find(PG_Annotation.datetime_end < input2 == 0);
if ~isempty(idx4)
    PG_Annotation(idx4,:) = [];
end

datenum_begin_PG = datenum(PG_Annotation.datetime_begin);
datenum_end_PG = datenum(PG_Annotation.datetime_end);
datenum_PG = [datenum_begin_PG, datenum_end_PG]; %in second


elapsed_time.PG_vector_creation = toc;


%% Output Aplose
%The timevector is looked over, at every timebin we check if there is an
%overlapping Aplose annotation, if so, output_Ap = 1, if not output_Ap = 0
if skip_Ap == 0
    tic
    interval_Ap = [datenum_begin_Ap+(0.1*time_bin/3600/24), datenum_end_Ap-(0.1*time_bin/3600/24)]; %Aplose annotations intervals +/-10% of time bin in order to avoid any overlap on several timebin
    interval_time = [ datenum_time((1:end-1),1), datenum_time((2:end),1)]; %Time intervals

    output_Ap = false(length(interval_time),1);
    idx_overlap = [];
    k=1;
    for i = 1:length(interval_time)
        inter=[];
        for j = k:length(interval_Ap)
            inter(j,1) = intersection_vect(interval_time(i,:), interval_Ap(j,:))  ;
        end
        idx_overlap = find(inter==1); %indexes of overlapping Ap annotations(j) with timebox(i)
        if ~isempty(idx_overlap)
            k = idx_overlap(end);
        end
        
        if length(idx_overlap) > 1 %More than 1 overlap
            disp(['More than one overlap : '])
            disp(['   interval_time(i) with i = ',num2str(i)])
            disp(['   interval_Ap(j) with j =  ',num2str(idx_overlap')])
            
%             lines to help debugging:
%             datetime(interval_time(i,:), 'ConvertFrom', 'datenum')
%             datetime(interval_Ap(382,:), 'ConvertFrom', 'datenum')
%             datetime(interval_Ap(383,:), 'ConvertFrom', 'datenum')
%             intersection_vect(interval_time(i,:), interval_Ap(382,:))
%             intersection_vect(interval_time(i,:), interval_Ap(383,:))
%             overlap_rate(interval_time(i,:), interval_Ap(382,:))
%             overlap_rate(interval_time(i,:), interval_Ap(383,:))

            return
        elseif length(idx_overlap) == 1
            output_Ap(i,1) = true;
        elseif length(idx_overlap) == 0
            output_Ap(i,1) = false;
        end
        clc;disp([num2str(i),'/',num2str(length(interval_time))])
    end
elapsed_time.output_Ap = toc;
end

%% Output PG
%Same than previous section but with PG detections
tic

interval_PG = [datenum_begin_PG, datenum_end_PG]; %PG detection intervals
interval_time = [ datenum_time((1:end-1),1), datenum_time((2:end),1)]; %Time intervals

output_PG = false(length(interval_time),1);
idx_overlap = [];
k=1;
for i = 1:length(interval_time)
    inter=[];
    for j = k:length(interval_PG)
        inter(j,1) = intersection_vect(interval_time(i,:), interval_PG(j,:))  ;
    end

    idx_overlap = find(inter==1); %indexes of overlapping PG detections(j) with timebox(i)
    
    if ~isempty(idx_overlap)
        k = idx_overlap(end);
        nb_overlap = length(idx_overlap);
    end
    
    %output_PG
    %if a click detector is being analysed then is_click == 1 then for each timebin 
    %output_PG will return the numbers of individual click detections.
    %if is_click == 0, then output_PG returns 0 or 1 if there are detection
    %for the timebin(i) or not.
    if length(idx_overlap) >= 1  
        output_PG(i,1) = true;
        if is_click==1
            nb_click(i,1) = nb_overlap;
        end
    elseif length(idx_overlap) == 0
        output_PG(i,1) = false;
    end


    clc;disp([num2str(i),'/',num2str(length(interval_time))])
end

%Conversion from PG detection to Aplose equivalent boxes
interval_PG_formatted = interval_time(find(output_PG),:);

start_time = zeros( length(interval_PG_formatted),1 );
start_frequency = zeros( length(interval_PG_formatted),1 );
end_time = ones( length(interval_PG_formatted),1 )*time_bin;
end_frequency = ones( length(interval_PG_formatted),1 )*60000;
if skip_Ap == 0
    annotation = repmat(type_selected,[length(interval_PG_formatted),1]);
elseif skip_Ap == 1
    type_selected='whistle and moan detector';
    annotation = repmat(type_selected,[length(interval_PG_formatted),1]);
end


clearvars start_datetime end_datetime
for i = 1:length(interval_PG_formatted)
    start_datetime(i,1) = datetime(interval_PG_formatted(i,1), 'ConvertFrom', 'datenum');
    end_datetime(i,1) = datetime(interval_PG_formatted(i,2), 'ConvertFrom', 'datenum');
end
PG_Annotation_formatted = table(start_time, end_time, start_frequency, end_frequency, start_datetime, end_datetime, annotation); %export format Aplose des detections PG

if is_click == 1
    threshold_click = 1*median(nb_click);
    threshold_click2 = median(nb_click(output_Ap))

    click_window = find(nb_click>threshold_click);
    PG_Annotation_formatted_sorted = PG_Annotation_formatted(click_window,:);
    bar(nb_click) %Amount of clik VS timebin
%     yline(threshold_click) %Threshold
%     yline(threshold_click*2) %Threshold
%     yline(threshold_click2) %Threshold
end


elapsed_time.output_PG = toc;
if skip_Ap == 0
    elapsed_time.total_elapsed  = elapsed_time.time_vector_creation + elapsed_time.Ap_vector_creation +elapsed_time.PG_vector_creation +elapsed_time.output_Ap +elapsed_time.output_PG;
end

%% Results
if skip_Ap == 0
    output_Ap(index_exclude) = [];
end
output_PG(index_exclude) = [];
% time_vector(index_exclude) = [];
% duration_time(index_exclude) = [];


if skip_Ap == 0
    comparison = "";
    for i = 1:length(output_PG)
        if output_PG(i) == 1
            if output_Ap(i) == 1
                comparison(i,1) = "VP";
            elseif output_Ap(i) == 0
                comparison(i,1) = "FP";
            else
                comparison(i,1) = "erreur999";
            end
        elseif output_PG(i) == 0
            if output_Ap(i) == 1
                comparison(i,1) = "FN";
            elseif output_Ap(i) == 0
                comparison(i,1) = "VN";
            else
                comparison(i,1) = "erreur998";
            end
        else
            comparison(i,1) = "erreur997";
        end
    end

    results.nb_total = length(output_PG);
    results.nb_VN = length(find(comparison == "VN"));
    results.nb_VP = length(find(comparison == "VP"));
    results.nb_FP = length(find(comparison == "FP"));
    results.nb_FN = length(find(comparison == "FN"));
    results.nb_e = length(find(comparison == "erreur999"))+length(find(comparison == "erreur998"))+length(find(comparison == "erreur997"));

    results.precision = results.nb_VP/(results.nb_VP + results.nb_FP);
    results.recall = results.nb_VP/(results.nb_VP + results.nb_FN);

    clc
    disp(['Precision : ', num2str(results.precision), '; Recall : ', num2str(results.recall)])
    % disp(results)
    % disp(elapsed_time)
elseif skip_Ap == 1
    clc
    results.total = height(output_PG);
    results.detection = height(PG_Annotation_formatted);
    results.detection_rate = height(PG_Annotation_formatted)/height(output_PG)*100;
    
    disp(['total : ', num2str(height(output_PG)), '; détection : ', num2str(height(PG_Annotation_formatted)),...
        '; détection : ', num2str(height(PG_Annotation_formatted)/height(output_PG)*100),'%'])
end

%% Save results

date_folder = char(datetime(now,'ConvertFrom','datenum','Format','dd-MM_HHmmss'));
folder_result = strcat(Ap_datapath, 'Results\', date_folder);
mkdir(folder_result);

export_time2Raven(folder_result, WavFolderInfo, time_vector, time_bin, duration_time) %Time vector as Raven Table
export_PG2Raven(PG_Annotation, folder_result, WavFolderInfo) %unformatted PG detection as Raven table
export_Aplose2Raven(WavFolderInfo, PG_Annotation_formatted, folder_result, ' - PamGuard2Raven formatted Selection Table.txt') %Aplose-formatted PG detections as Raven table

dataset_name = "ST335556632 C2D1";
label= "whistle and moan detector";
annotator = "PAMGuard";
export_PG2Aplose(PG_Annotation_formatted,dataset_name, label, annotator, WavFolderInfo, folder_result) %Aplose-formatted PG detections as Aplose output file

if skip_Ap == 0
    
    D = [results.nb_total, results.nb_VP, results.nb_FP, results.nb_VN, results.nb_FN, results.precision, results.recall  ];

    file_name = [strcat(folder_result,'\', WavFolderInfo.txt_filename, ' - results_',date_folder,'.csv')];
    selec_table = fopen(file_name, 'wt');
    fprintf(selec_table,'%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n %.0f\t%.0f\t%.0f\t%.0f\t%.0f\t%.0f\t%.0f\t%.4f\t%.4f\t%.0f\t',...
        'nb_total','nb_annotation','nb_detection', 'VP', 'FP', 'VN', 'FN', 'Precision', 'Recall', 'Elapsed time',...
        results.nb_total, sum(output_Ap), sum(output_PG), results.nb_VP, results.nb_FP, results.nb_VN, results.nb_FN, results.precision, results.recall, elapsed_time.total_elapsed);
    fclose('all');

    %export output file
    x = [1:1:length(output_Ap)]';
    if is_click == 1
        nb_click2 = nb_click(setdiff(1:length(nb_click), index_exclude));
        y = [x, output_Ap, nb_click2]';
    else
        y = [x, output_Ap, output_PG]';
    end
    fileID = fopen(strcat(folder_result,'\', WavFolderInfo.txt_filename, ' - output_',date_folder,'.csv'),'w');
    fprintf(fileID,'%s \t%s \t%s\r\n','x','output_Ap','output_PG');
    fprintf(fileID,'%.0f\t %.0f\t %.0f\r\n', y);
    fclose(fileID);

    export_Aplose2Raven(WavFolderInfo, Ap_Annotation , folder_result) %export Aplose annotation as Raven table
    
end

clc;disp(strcat("Results and tables saved in ", folder_result));
fprintf('\nResults :\n')
disp(results)
fprintf('\nElapsed time :\n')
disp(elapsed_time)
