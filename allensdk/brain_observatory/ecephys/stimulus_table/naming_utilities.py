# import re


# DIGIT_NAMES = {
#     '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
# }


# GABOR_DIAMETER_RE = re.compile('gabor_(\d+)_deg_250ms')
# MOVIE_NUMBER_NUMERAL_RE = re.compile('natural_movie_(?P<movie_number>\d+)(_more_repeats)')
# ANY_ENGLISH = '|'.join(DIGIT_NAMES.values())
# MOVIE_NUMBER_ENGLISH_RE = re.compile(f'natural_movie_(?P{ANY_ENGLISH})(_more_repeats)')


# def munge_gabor_stim_name(table, gabor_name=gabor, gabor_diameter_regex=GABOR_DIAMETER_RE):
#     ''' the gabor_20_deg_250ms stimulus has diameter (a parameter we want) and duration (a parameter encoded already by start and stop times)
#     baked into the name. This function splits them out.
#     '''

#     table['diameter'] = table['stimulus_name'].str.extract(gabor_diameter_regex)
#     table['stimulus_name'][~table['diameter'].isna()] = gabor_name
#     return table


# def munge_natural_movie_shuffled_stim_name(table, natural_movie_shuffled_key='natural_movie_shuffled', movie_number_regex=MOVIE_NUMBER_RE):
#     # special case the natural_movie_shuffled stimulus
#     # TODO: geez ...

#     unique_names = table['stimulus_name'].unique()
#     movie_numbers = set()

#     for name in unique_names:
#         match = MOVIE_NUMBER_RE.match(name)
#         if match is None:
#             continue
#         movie_numbers.add(match['movie_number'])

#     if natural_movie_shuffled_key in unique_names:
#         movie_numbers = list(movie_numbers)
#         if len(movie_numbers) != 1:
#             raise ValueError(f'unable to uniquely identify the natural movie used for \'{natural_movie_shuffled_key}\' (candidates: {movie_numbers})')
        
#         key = movie_numbers[0]


# def munge_names(table, stimulus_name_map, column_name_map): # TODO: when possible, delete this function

#     table = munge_gabor_stim_name(table)
#     table = munge_movie_numbers(table)

#     if stimulus_name_map is not None:
#         table['stimulus_name'].fillna('', inplace=True) # exposes no-stim condition as empty string
#         table['stimulus_name'].replace(to_replace=stimulus_name_map, inplace=True)
#         table['stimulus_name'].replace(to_replace={'': np.nan}, inplace=True)
#     if column_name_map is not None:
#         table.rename(columns=column_name_map, inplace=True)


# def replace_movie_numerals(
#     table, 
#     name_col='stimulus_name', 
#     natural_movie_re=MOVIE_NUMBER_NUMERAL_RE, 
#     digit_names=DIGIT_NAMES, 
#     tmp_col='__throwaway__'
# ):
#     ''' map stimulus names like e.g. "natural_movie_1" -> "natural_movie_one" for consistency 
#     with ophys.
#     '''

#     def renamer(row):
#         if row[tmp_col].isnull():
#             return row[name_col]
#         return row[name_col].replace(digit_names[row[tmp_col]])

#     table[tmp_col] = table[name_col].str.match(natural_movie_re)
#     table[name_col] = table.apply(renamer, axis=0)
#     table.drop(tmp_col)

#     return table