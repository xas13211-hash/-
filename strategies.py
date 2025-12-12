# backend/strategies.py
import pandas_ta as ta
import pandas as pd
import numpy as np

class BaseStrategy:
    def __init__(self):
        self.name = "기본 전략"
        self.risk_level = "Stable"
        self.leverage = 1.0
        self.risk_percent = 5.0
        self.description = "기본 베이스 전략입니다."

    def calculate_signals(self, df):
        # 기본적으로 아무 신호도 없음 (signal 컬럼 0으로 초기화)
        df['signal'] = 0
        return df

# [0] Default
class NoStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "전략 미선택 (대기)"
        self.risk_level = "None"
        self.description = "아무런 매매도 하지 않는 대기 상태입니다."

    def calculate_signals(self, df):
        df = df.copy()
        df['signal'] = 0
        return df

# --- Trend Following Strategies (추세 추종) ---

# [1] SMA Cross
class SmaCrossStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "SMA 크로스 (단순이동평균)"
        self.risk_level = "Stable"
        self.description = "단기(5)와 장기(20) 단순이동평균선의 교차를 이용한 전략"

    def calculate_signals(self, df):
        df = df.copy()
        df['ma5'] = ta.sma(df['close'], length=5)
        df['ma20'] = ta.sma(df['close'], length=20)
        df['signal'] = 0
        
        # Golden Cross
        cond_buy = (df['ma5'] > df['ma20']) & (df['ma5'].shift(1) <= df['ma20'].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        # Death Cross
        cond_sell = (df['ma5'] < df['ma20']) & (df['ma5'].shift(1) >= df['ma20'].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [2] EMA Cross
class EmaCrossStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "EMA 크로스 (지수이동평균)"
        self.risk_level = "Stable"
        self.description = "단기(9)와 장기(21) 지수이동평균선의 교차를 이용한 전략"

    def calculate_signals(self, df):
        df = df.copy()
        df['ema9'] = ta.ema(df['close'], length=9)
        df['ema21'] = ta.ema(df['close'], length=21)
        df['signal'] = 0
        
        cond_buy = (df['ema9'] > df['ema21']) & (df['ema9'].shift(1) <= df['ema21'].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['ema9'] < df['ema21']) & (df['ema9'].shift(1) >= df['ema21'].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [3] MACD
class MacdStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "MACD 추세 추종"
        self.risk_level = "Moderate"
        self.description = "MACD선이 Signal선을 상향 돌파하면 매수, 하향 돌파하면 매도"

    def calculate_signals(self, df):
        df = df.copy()
        # macd, macdh(hist), macds(signal)
        macd = ta.macd(df['close'])
        if macd is None: return df
        
        df = pd.concat([df, macd], axis=1)
        
        macd_col = 'MACD_12_26_9'
        signal_col = 'MACDs_12_26_9'
        
        if macd_col not in df.columns: return df

        df['signal'] = 0
        cond_buy = (df[macd_col] > df[signal_col]) & (df[macd_col].shift(1) <= df[signal_col].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df[macd_col] < df[signal_col]) & (df[macd_col].shift(1) >= df[signal_col].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [4] ADX Trend
class AdxStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "ADX 강한 추세"
        self.risk_level = "Moderate"
        self.description = "ADX가 25 이상일 때 D+가 D-보다 높으면 매수 (강한 추세 추종)"

    def calculate_signals(self, df):
        df = df.copy()
        adx = ta.adx(df['high'], df['low'], df['close'])
        if adx is None: return df
        df = pd.concat([df, adx], axis=1)
        
        adx_col = 'ADX_14'
        dmp_col = 'DMP_14'
        dmn_col = 'DMN_14'
        
        if adx_col not in df.columns: return df
        
        df['signal'] = 0
        strong_trend = df[adx_col] > 25
        
        cond_buy = strong_trend & (df[dmp_col] > df[dmn_col]) & (df[dmp_col].shift(1) <= df[dmn_col].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = strong_trend & (df[dmp_col] < df[dmn_col]) & (df[dmp_col].shift(1) >= df[dmn_col].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [5] Parabolic SAR
class ParabolicSarStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "파라볼릭 SAR"
        self.risk_level = "Aggressive"
        self.description = "SAR 점이 가격 아래에 있으면 매수, 위에 있으면 매도"

    def calculate_signals(self, df):
        df = df.copy()
        psar = ta.psar(df['high'], df['low'], df['close'])
        if psar is None: return df
        
        df = pd.concat([df, psar], axis=1)
        long_col = 'PSARl_0.02_0.2'
        short_col = 'PSARs_0.02_0.2'
        
        if long_col not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (~df[long_col].isna()) & (df[long_col].shift(1).isna())
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (~df[short_col].isna()) & (df[short_col].shift(1).isna())
        df.loc[cond_sell, 'signal'] = -1
        return df

# [6] Ichimoku Cloud
class IchimokuStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "일목균형표 (구름대)"
        self.risk_level = "Moderate"
        self.description = "전환선이 기준선을 상향 돌파하고 구름대 위에 있을 때 매수"

    def calculate_signals(self, df):
        df = df.copy()
        ichimoku = ta.ichimoku(df['high'], df['low'], df['close'])
        if ichimoku is None: return df
        
        trend_df = ichimoku[0]
        df = pd.concat([df, trend_df], axis=1)
        
        tenkan = 'ITS_9' # 전환선
        kijun = 'IKS_26' # 기준선
        span_a = 'ISA_9' # 선행스팬1
        span_b = 'ISB_26' # 선행스팬2
        
        if tenkan not in df.columns: return df
        
        df['signal'] = 0
        
        above_cloud = (df['close'] > df[span_a]) & (df['close'] > df[span_b])
        cross_up = (df[tenkan] > df[kijun]) & (df[tenkan].shift(1) <= df[kijun].shift(1))
        
        df.loc[cross_up & above_cloud, 'signal'] = 1
        
        below_cloud = (df['close'] < df[span_a]) & (df['close'] < df[span_b])
        cross_down = (df[tenkan] < df[kijun]) & (df[tenkan].shift(1) >= df[kijun].shift(1))
        
        df.loc[cross_down & below_cloud, 'signal'] = -1
        return df

# [7] Supertrend
class SupertrendStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "슈퍼트렌드 전략"
        self.risk_level = "Moderate"
        self.description = "슈퍼트렌드 지표의 추세 전환을 이용한 전략"

    def calculate_signals(self, df):
        df = df.copy()
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3.0)
        if st is None: return df
        df = pd.concat([df, st], axis=1)
        
        trend_col = 'SUPERTd_10_3.0'
        
        if trend_col not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df[trend_col] == 1) & (df[trend_col].shift(1) == -1)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df[trend_col] == -1) & (df[trend_col].shift(1) == 1)
        df.loc[cond_sell, 'signal'] = -1
        return df

# [8] Vortex Indicator
class VortexStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "Vortex (보텍스) 지표"
        self.risk_level = "Aggressive"
        self.description = "VI+가 VI-를 상향 돌파하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        vortex = ta.vortex(df['high'], df['low'], df['close'])
        if vortex is None: return df
        df = pd.concat([df, vortex], axis=1)
        
        vip = 'VTXP_14'
        vim = 'VTXM_14'
        
        if vip not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df[vip] > df[vim]) & (df[vip].shift(1) <= df[vim].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df[vip] < df[vim]) & (df[vip].shift(1) >= df[vim].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [9] TRIX
class TrixStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "TRIX (트릭스) 모멘텀"
        self.risk_level = "Moderate"
        self.description = "TRIX 선이 0선을 상향 돌파하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        trix = ta.trix(df['close'])
        if trix is None: return df
        df = pd.concat([df, trix], axis=1)
        
        trix_col = 'TRIX_30_9'
        signal_col = 'TRIXs_30_9'
        
        if trix_col not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df[trix_col] > df[signal_col]) & (df[trix_col].shift(1) <= df[signal_col].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df[trix_col] < df[signal_col]) & (df[trix_col].shift(1) >= df[signal_col].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# --- Mean Reversion Strategies (평균 회귀/역추세) ---

# [10] RSI Strategy
class RsiStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "RSI 역추세 (평균회귀)"
        self.risk_level = "Aggressive"
        self.description = "RSI 30 미만 과매도 매수, 70 초과 과매수 매도"

    def calculate_signals(self, df):
        df = df.copy()
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['signal'] = 0
        
        df.loc[(df['rsi'] < 30) & (df['rsi'].shift(1) >= 30), 'signal'] = 1
        df.loc[(df['rsi'] > 70) & (df['rsi'].shift(1) <= 70), 'signal'] = -1
        return df

# [11] Bollinger Bands Mean Reversion
class BollingerMeanRevStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "볼린저 밴드 (평균회귀)"
        self.risk_level = "Moderate"
        self.description = "볼린저 밴드 하단 터치 시 매수, 상단 터치 시 매도"

    def calculate_signals(self, df):
        df = df.copy()
        bb = ta.bbands(df['close'], length=20, std=2)
        if bb is None: return df
        df = pd.concat([df, bb], axis=1)
        
        lower = 'BBL_20_2.0'
        upper = 'BBU_20_2.0'
        
        if lower not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df['close'] < df[lower]) & (df['close'].shift(1) >= df[lower].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['close'] > df[upper]) & (df['close'].shift(1) <= df[upper].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [12] Stochastic Oscillator
class StochasticStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "스토캐스틱 오실레이터"
        self.risk_level = "Aggressive"
        self.description = "스토캐스틱 K가 D를 골든크로스(과매도 구간)하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        stoch = ta.stoch(df['high'], df['low'], df['close'])
        if stoch is None: return df
        df = pd.concat([df, stoch], axis=1)
        
        k = 'STOCHk_14_3_3'
        d = 'STOCHd_14_3_3'
        
        if k not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df[k] < 20) & (df[k] > df[d]) & (df[k].shift(1) <= df[d].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df[k] > 80) & (df[k] < df[d]) & (df[k].shift(1) >= df[d].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [13] CCI
class CciStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "CCI (상품채널지수)"
        self.risk_level = "Aggressive"
        self.description = "CCI -100 상향 돌파 시 매수, +100 하향 돌파 시 매도"

    def calculate_signals(self, df):
        df = df.copy()
        df['cci'] = ta.cci(df['high'], df['low'], df['close'])
        df['signal'] = 0
        
        cond_buy = (df['cci'] > -100) & (df['cci'].shift(1) <= -100)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['cci'] < 100) & (df['cci'].shift(1) >= 100)
        df.loc[cond_sell, 'signal'] = -1
        return df

# [14] Williams %R
class WilliamsRStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "윌리엄스 %R"
        self.risk_level = "Aggressive"
        self.description = "윌리엄스 %R -80 상향 돌파 시 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['willr'] = ta.willr(df['high'], df['low'], df['close'])
        df['signal'] = 0
        
        cond_buy = (df['willr'] > -80) & (df['willr'].shift(1) <= -80)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['willr'] < -20) & (df['willr'].shift(1) >= -20)
        df.loc[cond_sell, 'signal'] = -1
        return df



# [15] MFI
class MfiStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "MFI (자금흐름지수)"
        self.risk_level = "Moderate"
        self.description = "MFI(자금흐름지수) 과매도/과매수 전략"

    def calculate_signals(self, df):
        df = df.copy()
        
        # [수정] 데이터 타입 강제 변환 (에러/경고 해결)
        # int64 등으로 되어있을 수 있는 데이터를 float으로 바꿔서 넘겨야 함
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)
        vol = df['vol'].astype(float)

        df['mfi'] = ta.mfi(high, low, close, vol)
        df['signal'] = 0
        
        # (나머지 로직은 동일)
        cond_buy = (df['mfi'] < 20) & (df['mfi'].shift(1) >= 20)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['mfi'] > 80) & (df['mfi'].shift(1) <= 80)
        df.loc[cond_sell, 'signal'] = -1
        return df

# [16] Ultimate Oscillator
class UltimateOscStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "Ultimate (얼티밋) 오실레이터"
        self.risk_level = "Moderate"
        self.description = "UO 지표가 30 미만에서 상승 반전 시 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['uo'] = ta.uo(df['high'], df['low'], df['close'])
        df['signal'] = 0
        
        cond_buy = (df['uo'] < 30) & (df['uo'] > df['uo'].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['uo'] > 70) & (df['uo'] < df['uo'].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# --- Breakout / Momentum Strategies (돌파/모멘텀) ---

# [17] Bollinger Breakout
class BollingerBreakoutStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "볼린저 밴드 돌파"
        self.risk_level = "Aggressive"
        self.description = "볼린저 밴드 상단 돌파 시 매수 (추세 지속)"

    def calculate_signals(self, df):
        df = df.copy()
        bb = ta.bbands(df['close'], length=20, std=2)
        if bb is None: return df
        df = pd.concat([df, bb], axis=1)
        
        upper = 'BBU_20_2.0'
        lower = 'BBL_20_2.0'
        
        if upper not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df['close'] > df[upper]) & (df['close'].shift(1) <= df[upper].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['close'] < df[lower]) & (df['close'].shift(1) >= df[lower].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [18] Donchian Channels
class DonchianChannelStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "돈치안 채널 돌파"
        self.risk_level = "Stable"
        self.description = "20일 신고가 갱신 시 매수, 신저가 갱신 시 매도"

    def calculate_signals(self, df):
        df = df.copy()
        donchian = ta.donchian(df['high'], df['low'], lower_length=20, upper_length=20)
        if donchian is None: return df
        df = pd.concat([df, donchian], axis=1)
        
        upper = 'DCU_20_20'
        lower = 'DCL_20_20'
        
        if upper not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df['high'] >= df[upper].shift(1)) & (df['high'].shift(1) < df[upper].shift(2))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['low'] <= df[lower].shift(1)) & (df['low'].shift(1) > df[lower].shift(2))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [19] Keltner Channels
class KeltnerChannelStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "켈트너 채널 돌파"
        self.risk_level = "Moderate"
        self.description = "켈트너 채널 상단 돌파 시 매수"

    def calculate_signals(self, df):
        df = df.copy()
        kc = ta.kc(df['high'], df['low'], df['close'])
        if kc is None: return df
        df = pd.concat([df, kc], axis=1)
        
        upper = 'KCUe_20_2'
        lower = 'KCLe_20_2'
        
        if upper not in df.columns: return df
        
        df['signal'] = 0
        cond_buy = (df['close'] > df[upper]) & (df['close'].shift(1) <= df[upper].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['close'] < df[lower]) & (df['close'].shift(1) >= df[lower].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [20] ROC
class RocStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "ROC (변화율) 모멘텀"
        self.risk_level = "Aggressive"
        self.description = "ROC가 0선을 상향 돌파하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['roc'] = ta.roc(df['close'], length=10)
        df['signal'] = 0
        
        cond_buy = (df['roc'] > 0) & (df['roc'].shift(1) <= 0)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['roc'] < 0) & (df['roc'].shift(1) >= 0)
        df.loc[cond_sell, 'signal'] = -1
        return df

# [21] Awesome Oscillator
class AwesomeOscStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "AO (어썸 오실레이터)"
        self.risk_level = "Moderate"
        self.description = "AO가 0선을 상향 돌파하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['ao'] = ta.ao(df['high'], df['low'])
        df['signal'] = 0
        
        cond_buy = (df['ao'] > 0) & (df['ao'].shift(1) <= 0)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['ao'] < 0) & (df['ao'].shift(1) >= 0)
        df.loc[cond_sell, 'signal'] = -1
        return df

# [22] Hull MA
class HullMaStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "Hull MA (헐 이동평균)"
        self.risk_level = "Aggressive"
        self.description = "빠른 반응속도의 Hull MA 기울기 상승 시 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['hma'] = ta.hma(df['close'], length=20)
        df['signal'] = 0
        
        cond_buy = (df['hma'] > df['hma'].shift(1)) & (df['hma'].shift(1) <= df['hma'].shift(2))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['hma'] < df['hma'].shift(1)) & (df['hma'].shift(1) >= df['hma'].shift(2))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [23] Triple EMA
class TemaStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "TEMA (삼중지수이동평균)"
        self.risk_level = "Aggressive"
        self.description = "TEMA가 가격을 상향 돌파하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['tema'] = ta.tema(df['close'], length=20)
        df['signal'] = 0
        
        cond_buy = (df['close'] > df['tema']) & (df['close'].shift(1) <= df['tema'].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['close'] < df['tema']) & (df['close'].shift(1) >= df['tema'].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [24] VWMA
class VwmaStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "VWMA (거래량가중이동평균)"
        self.risk_level = "Stable"
        self.description = "SMA가 VWMA를 상향 돌파하면 매수 (거래량 실린 상승)"

    def calculate_signals(self, df):
        df = df.copy()
        df['sma'] = ta.sma(df['close'], length=20)
        df['vwma'] = ta.vwma(df['close'], df['vol'], length=20)
        df['signal'] = 0
        
        cond_buy = (df['sma'] > df['vwma']) & (df['sma'].shift(1) <= df['vwma'].shift(1))
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['sma'] < df['vwma']) & (df['sma'].shift(1) >= df['vwma'].shift(1))
        df.loc[cond_sell, 'signal'] = -1
        return df

# [25] CMF
class CmfStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.name = "CMF (채이킨 자금흐름)"
        self.risk_level = "Moderate"
        self.description = "CMF가 0선을 상향 돌파하면 매수"

    def calculate_signals(self, df):
        df = df.copy()
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['vol'], length=20)
        df['signal'] = 0
        
        cond_buy = (df['cmf'] > 0) & (df['cmf'].shift(1) <= 0)
        df.loc[cond_buy, 'signal'] = 1
        
        cond_sell = (df['cmf'] < 0) & (df['cmf'].shift(1) >= 0)
        df.loc[cond_sell, 'signal'] = -1
        return df


# --- Strategy Map ---
STRATEGY_MAP = {
    0: NoStrategy(),
    1: SmaCrossStrategy(),
    2: EmaCrossStrategy(),
    3: MacdStrategy(),
    4: AdxStrategy(),
    5: ParabolicSarStrategy(),
    6: IchimokuStrategy(),
    7: SupertrendStrategy(),
    8: VortexStrategy(),
    9: TrixStrategy(),
    10: RsiStrategy(),
    11: BollingerMeanRevStrategy(),
    12: StochasticStrategy(),
    13: CciStrategy(),
    14: WilliamsRStrategy(),
    15: MfiStrategy(),
    16: UltimateOscStrategy(),
    17: BollingerBreakoutStrategy(),
    18: DonchianChannelStrategy(),
    19: KeltnerChannelStrategy(),
    20: RocStrategy(),
    21: AwesomeOscStrategy(),
    22: HullMaStrategy(),
    23: TemaStrategy(),
    24: VwmaStrategy(),
    25: CmfStrategy()
}